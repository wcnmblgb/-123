#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
snake/core.py — 贪吃蛇游戏核心逻辑（纯 Python，零第三方依赖）

设计要点
========
* **逻辑与界面彻底分离**：本模块不知道 tkinter/curses 的存在，
  因此可以用 unittest 在无显示器环境下完整测试。
* **确定性可复现**：随机数通过 ``random.Random`` 实例注入，
  传入相同的 seed 就能得到完全相同的食物序列。
* **一个 tick 一步**：``step()`` 只在「时间前进一格」时被调用，
  界面层负责把「真实时间」换算成 tick，核心逻辑不碰 time.sleep。

坐标约定
========
``(x, y)``，x 向右递增，y 向下递增，原点 (0, 0) 在**左上角**。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Iterator

# ============================================================
#  方向
# ============================================================


class Direction(Enum):
    """四个移动方向。value 是 (dx, dy) 位移向量。"""

    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

    @property
    def vector(self) -> tuple[int, int]:
        """返回位移向量，例如 ``Direction.UP.vector == (0, -1)``。"""
        return self.value  # type: ignore[return-value]

    @property
    def opposite(self) -> "Direction":
        """返回相反方向，用于拦截「原地掉头」。"""
        dx, dy = self.vector
        return Direction((-dx, -dy))


# ============================================================
#  配置与异常
# ============================================================


class SnakeError(Exception):
    """本游戏所有自定义异常的基类。"""


class GameOverError(SnakeError):
    """在游戏结束后继续操作时抛出（例如对已结束的局调用 step）。"""


@dataclass
class GameConfig:
    """
    游戏规则配置。

    :param width:          棋盘宽度（格）
    :param height:         棋盘高度（格）
    :param start_length:   初始蛇身长度
    :param wrap:           True = 穿墙（从另一侧出现）；False = 撞墙即死
    :param foods_per_level: 每吃多少个食物升一级
    :param base_ticks:     1 级时每秒走多少格
    :param max_ticks:      最高级时每秒走多少格
    :param max_level:      等级上限
    """

    width: int = 24
    height: int = 20
    start_length: int = 3
    wrap: bool = False
    foods_per_level: int = 5
    base_ticks: float = 6.0
    max_ticks: float = 18.0
    max_level: int = 10

    def __post_init__(self) -> None:
        if self.width < 3 or self.height < 3:
            raise ValueError("棋盘至少需要 3x3")
        if self.start_length + 2 > self.width:
            raise ValueError(
                f"初始长度 {self.start_length} 相对于棋盘宽度 {self.width} 过大"
                f"（需要 width >= start_length + 2）"
            )
        free_cells = self.width * self.height - self.start_length
        if free_cells < 1:
            raise ValueError("初始蛇身已占满棋盘，没有放食物的空间")
        if self.foods_per_level < 1:
            raise ValueError("foods_per_level 至少为 1")
        if not 0 < self.base_ticks <= self.max_ticks:
            raise ValueError("速度参数不合法：需要 0 < base_ticks <= max_ticks")
        if self.max_level < 1:
            raise ValueError("max_level 至少为 1")

    # ---- 派生属性 ----

    @property
    def cell_count(self) -> int:
        """棋盘总格数。"""
        return self.width * self.height

    def contains(self, pos: tuple[int, int]) -> bool:
        """判断坐标是否在棋盘内（不做环绕处理）。"""
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def cells(self) -> Iterator[tuple[int, int]]:
        """按行优先顺序遍历所有格子。"""
        for y in range(self.height):
            for x in range(self.width):
                yield (x, y)


# ============================================================
#  核心游戏
# ============================================================


class SnakeGame:
    """
    贪吃蛇核心状态机。

    典型用法::

        game = SnakeGame()
        game.turn(Direction.DOWN)
        result = game.step()          # 前进一步
        if result.ate_food:
            print("吃到食物，得分", game.score)

    蛇身使用 ``list`` 存储，**索引 0 是蛇头**，末尾是蛇尾。
    """

    # 合法状态
    STATE_READY = "ready"      # 已就绪，第一步尚未走出
    STATE_RUNNING = "running"
    STATE_PAUSED = "paused"
    STATE_OVER = "over"

    def __init__(
        self,
        config: GameConfig | None = None,
        *,
        seed: int | None = None,
        rng: random.Random | None = None,
    ) -> None:
        """
        :param config: 规则配置，默认 ``GameConfig()``
        :param seed:   随机种子（用于可复现的食物序列）
        :param rng:    直接注入 ``random.Random`` 实例（优先于 seed）
        """
        self.config = config or GameConfig()
        self._rng = rng if rng is not None else random.Random(seed)

        self.snake: list[tuple[int, int]] = []
        self.food: tuple[int, int] | None = None
        self.direction = Direction.RIGHT
        self._pending: list[Direction] = []

        self.state = self.STATE_READY
        self.score = 0
        self.high_score = 0
        self.foods_eaten = 0
        self.ticks = 0
        self._level = 1
        self.death_reason: str | None = None

        self._reset_board()

    # ------------------------------------------------------------
    #  初始化 / 重置
    # ------------------------------------------------------------

    def _reset_board(self) -> None:
        """把蛇放回棋盘中央，朝向右侧。"""
        cfg = self.config
        cx, cy = cfg.width // 2, cfg.height // 2
        # 蛇头在 (cx, cy)，身体向左延伸
        self.snake = [(cx - i, cy) for i in range(cfg.start_length)]
        self.direction = Direction.RIGHT
        self._pending.clear()
        self.food = self._spawn_food()

    def reset(self) -> None:
        """开新一局（保留历史最高分）。"""
        self.high_score = max(self.high_score, self.score)
        self.score = 0
        self.foods_eaten = 0
        self.ticks = 0
        self._level = 1
        self.death_reason = None
        self.state = self.STATE_READY
        self._reset_board()

    # ------------------------------------------------------------
    #  只读属性
    # ------------------------------------------------------------

    @property
    def head(self) -> tuple[int, int]:
        """蛇头坐标。"""
        return self.snake[0]

    @property
    def length(self) -> int:
        """当前蛇长（格）。"""
        return len(self.snake)

    @property
    def level(self) -> int:
        """当前等级，随吃到的食物数量提升，上限 ``config.max_level``。"""
        return self._level

    @property
    def is_over(self) -> bool:
        """本局是否已结束。"""
        return self.state == self.STATE_OVER

    @property
    def ticks_per_second(self) -> float:
        """当前等级对应的速度（格/秒），界面层用它换算帧间隔。"""
        cfg = self.config
        if cfg.max_level == 1:
            return cfg.max_ticks
        span = cfg.max_ticks - cfg.base_ticks
        return cfg.base_ticks + span * (self._level - 1) / (cfg.max_level - 1)

    @property
    def tick_interval_ms(self) -> int:
        """当前等级对应的帧间隔（毫秒），供 tkinter ``after()`` 使用。"""
        return max(1, round(1000.0 / self.ticks_per_second))

    @property
    def occupancy(self) -> set[tuple[int, int]]:
        """蛇身占据的所有格子（集合，便于 O(1) 查询）。"""
        return set(self.snake)

    def is_win(self) -> bool:
        """是否已铺满整个棋盘。"""
        return self.length >= self.config.cell_count

    # ------------------------------------------------------------
    #  输入
    # ------------------------------------------------------------

    def turn(self, direction: Direction) -> bool:
        """
        请求改变方向。

        会把方向放进待处理队列，**每个 tick 只消费一个**，
        这样玩家快速连按（例如「上→左」两帧内按下）不会被吞掉，
        同时拦截「原地掉头」这种必死操作。

        :return: True 表示该方向被接受并排队
        """
        if self.is_over:
            return False

        # 与「最后一次生效/排队的方向」相反则拒绝
        reference = self._pending[-1] if self._pending else self.direction
        if direction is reference.opposite:
            return False
        if direction is reference:
            # 同方向重复按下：无需排队，避免队列膨胀
            return True

        # 队列上限 2，防止玩家乱按导致转向延迟过大
        if len(self._pending) >= 2:
            self._pending.pop(0)
        self._pending.append(direction)

        # 首次转向即开始游戏（READY → RUNNING）
        if self.state == self.STATE_READY:
            self.state = self.STATE_RUNNING
        return True

    def toggle_pause(self) -> str:
        """在 running/paused 之间切换，返回切换后的状态。"""
        if self.state == self.STATE_RUNNING:
            self.state = self.STATE_PAUSED
        elif self.state == self.STATE_PAUSED:
            self.state = self.STATE_RUNNING
        return self.state

    # ------------------------------------------------------------
    #  推进一帧
    # ------------------------------------------------------------

    def _wrap(self, pos: tuple[int, int]) -> tuple[int, int]:
        """把越界坐标环绕到棋盘另一侧。"""
        cfg = self.config
        return (pos[0] % cfg.width, pos[1] % cfg.height)

    def _next_head(self, direction: Direction) -> tuple[int, int]:
        """根据方向计算下一格蛇头坐标（按需环绕）。"""
        dx, dy = direction.vector
        nx, ny = self.head[0] + dx, self.head[1] + dy
        if self.config.wrap:
            return self._wrap((nx, ny))
        return (nx, ny)

    def step(self) -> "StepResult":
        """
        让时间前进一格。

        :raises GameOverError: 本局已结束或正在暂停
        :return: ``StepResult``，描述这一帧发生了什么
        """
        if self.state == self.STATE_OVER:
            raise GameOverError("本局已结束，请先调用 reset()")
        if self.state == self.STATE_PAUSED:
            raise GameOverError("游戏暂停中，请先恢复")

        # 检查是否已铺满棋盘
        if self.is_win():
            return self._finish("win", "已铺满棋盘，通关！")

        # 消费一个待处理方向
        moved_direction = self.direction
        if self._pending:
            moved_direction = self._pending.pop(0)
            self.direction = moved_direction

        new_head = self._next_head(moved_direction)

        # 撞墙判定
        if not self.config.contains(new_head):
            return self._finish("wall", f"撞到{'墙' if not self.config.wrap else '边界'}")

        # 将要吃到食物？吃到则不缩尾（等于长一格）
        ate_food = new_head == self.food

        # 自撞判定：尾巴本帧若会移开，则该格是安全的
        body = self.snake if ate_food else self.snake[:-1]
        if new_head in body:
            return self._finish("self", "咬到自己了")

        # 正式移动
        self.snake.insert(0, new_head)
        if not ate_food:
            self.snake.pop()

        self.ticks += 1

        if ate_food:
            self.score += 10 * self._level
            self.foods_eaten += 1
            old_level = self._level
            self._level = min(
                self.config.max_level,
                self.foods_eaten // self.config.foods_per_level + 1,
            )
            self.food = self._spawn_food()
            if self.is_win():
                return self._finish(
                    "win", "已铺满棋盘，通关！", ate_food=True,
                    level_changed=self._level != old_level,
                )
            return StepResult(
                ate_food=True,
                game_over=False,
                level_changed=self._level != old_level,
            )

        return StepResult(ate_food=False, game_over=False, level_changed=False)

    def _finish(
        self,
        reason: str,
        message: str,
        *,
        ate_food: bool = False,
        level_changed: bool = False,
    ) -> "StepResult":
        """结束本局并生成结果对象。"""
        self.state = self.STATE_OVER
        self.death_reason = reason
        self.high_score = max(self.high_score, self.score)
        return StepResult(
            ate_food=ate_food,
            game_over=True,
            level_changed=level_changed,
            reason=reason,
            message=message,
        )

    # ------------------------------------------------------------
    #  食物
    # ------------------------------------------------------------

    def _free_cells(self) -> list[tuple[int, int]]:
        """返回所有没有被蛇占据的格子。"""
        occupied = self.occupancy
        return [c for c in self.config.cells() if c not in occupied]

    def _spawn_food(self) -> tuple[int, int] | None:
        """
        在空格中随机放一个食物。

        :return: 食物坐标；棋盘已满时返回 None
        """
        free = self._free_cells()
        if not free:
            return None
        return self._rng.choice(free)


# ============================================================
#  一帧的结果
# ============================================================


@dataclass(frozen=True)
class StepResult:
    """``SnakeGame.step()`` 的返回值。"""

    ate_food: bool
    game_over: bool
    level_changed: bool
    reason: str | None = None
    message: str = ""

    @property
    def reward(self) -> int:
        """给 AI 用的即时奖励：吃到食物 +1，死亡 -1，其余 0。"""
        if self.game_over:
            return -1
        return 1 if self.ate_food else 0


# ============================================================
#  简单 AI（用于 --demo 演示与自动化测试）
# ============================================================


def _reachable_area(
    start: tuple[int, int],
    blocked: set[tuple[int, int]],
    config: GameConfig,
    limit: int = 4096,
) -> int:
    """
    在只考虑 ``blocked`` 障碍的前提下，从 ``start`` 出发能走到的格子数。

    用于 AI 判断「这一步走完之后还剩多少活动空间」。

    注意：``start`` 本身会从 ``blocked`` 里剔除 —— 蛇头所在的那一格当然属于
    蛇身，但它不能挡住自己。
    """
    blocked = set(blocked)
    blocked.discard(start)
    seen = {start}
    stack = [start]
    while stack and len(seen) < limit:
        x, y = stack.pop()
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx, ny = x + dx, y + dy
            if config.wrap:
                nx, ny = nx % config.width, ny % config.height
            elif not config.contains((nx, ny)):
                continue
            nxt = (nx, ny)
            if nxt in seen or nxt in blocked:
                continue
            seen.add(nxt)
            stack.append(nxt)
    return len(seen)


def _bfs_first_step(
    head: tuple[int, int],
    target: tuple[int, int],
    blocked: set[tuple[int, int]],
    config: GameConfig,
    limit: int = 2048,
) -> tuple[int, int] | None:
    """
    广度优先搜索从 ``head`` 到 ``target`` 的最短路，返回**第一步**的格子。

    这比「哪一步离食物更近就迈哪一步」可靠得多：贪心距离会让蛇贴着自己的身体
    绕圈，永远走不到食物跟前。

    :param blocked: 不可通行的格子（蛇身）。目标格即使出现在 blocked 里也会被
                    放行 —— 要搜的就是「走到食物那一格」。
    :param limit:   最多展开多少个格子，防止在大棋盘上搜索过久
    :return: 下一步坐标；不可达或超出搜索上限时返回 None
    """
    if head == target:
        return None

    from collections import deque

    queue: deque[tuple[int, int]] = deque([head])
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {head: None}
    expanded = 0

    while queue and expanded < limit:
        current = queue.popleft()
        expanded += 1

        for direction in Direction:
            dx, dy = direction.vector
            nx, ny = current[0] + dx, current[1] + dy
            if config.wrap:
                nx, ny = nx % config.width, ny % config.height
            elif not config.contains((nx, ny)):
                continue
            nxt = (nx, ny)
            if nxt in came_from:
                continue
            # 目标格无条件放行（调用方可能把它一并放进了 blocked）
            if nxt in blocked and nxt != target:
                continue

            came_from[nxt] = current
            if nxt == target:
                # 回溯：退到「父节点就是起点」的那一格，它就是第一步
                step = nxt
                while came_from[step] != head:
                    step = came_from[step]  # type: ignore[assignment]
                return step
            queue.append(nxt)

    return None


def choose_direction(game: SnakeGame, stagnation: int = 0) -> Direction | None:
    """
    AI 决策：两条简单且可验证的规则。

    1. **有路就走**：用 BFS 求到食物的最短路，走第一步（不绕圈、不撞自己）；
    2. **没路就活**：走到食物的路被自己的身体挡住时，改选「走完之后剩余活动
       空间最大」的方向，让蛇尽量撑到路打开为止。

    ``stagnation`` 只在第 1 条上起作用：长时间吃不到食物说明当前路径在兜圈子，
    此时暂停寻路、强制改用第 2 条规则换条路走，避免在两个格子之间来回摆动。

    :param stagnation: 距离上次进食的帧数
    :return: 选中的方向；完全无路可走时返回 None
    """
    if game.is_over or game.food is None:
        return None

    cfg = game.config
    head = game.head
    body = game.snake
    occupied = set(body)
    tail = body[-1]

    # 收集所有「不会立刻死」的候选
    candidates: list[dict] = []
    for direction in Direction:
        if direction is game.direction.opposite:
            continue

        dx, dy = direction.vector
        nx, ny = head[0] + dx, head[1] + dy
        if cfg.wrap:
            nx, ny = nx % cfg.width, ny % cfg.height
        elif not cfg.contains((nx, ny)):
            continue
        nxt = (nx, ny)

        # 尾巴本帧会让开，所以尾格可以通过
        if nxt in occupied and nxt != tail:
            continue

        new_body = [nxt] + body[:-1]
        blocked = set(new_body) - {new_body[-1], nxt}
        candidates.append({
            "direction": direction,
            "pos": nxt,
            "space": _reachable_area(nxt, blocked, cfg),
        })

    if not candidates:
        return None

    # ---- 规则 1：沿最短路去吃食物 ----
    if stagnation < 60:
        # 尾格本帧会让开，搜索时可以通行
        step = _bfs_first_step(head, game.food, occupied - {tail}, cfg)
        if step is not None:
            for item in candidates:
                if item["pos"] == step:
                    return item["direction"]

    # ---- 规则 2：路被自己挡住 → 往最开阔的方向走，等路打开 ----
    return min(candidates, key=lambda item: -item["space"])["direction"]


def ai_autoplay(game: SnakeGame, max_ticks: int = 5000) -> int:
    """
    让 AI 一直玩到游戏结束或达到 ``max_ticks``。

    :return: 实际执行的 tick 数
    """
    played = 0
    stagnation = 0
    foods_eaten = game.foods_eaten

    while played < max_ticks and not game.is_over:
        direction = choose_direction(game, stagnation)
        if direction is None:
            break
        game.turn(direction)
        game.step()
        played += 1

        if game.foods_eaten > foods_eaten:
            foods_eaten = game.foods_eaten
            stagnation = 0
        else:
            stagnation += 1

    # 铺满棋盘 / 无路可走时也把状态定格为结束，方便调用方判断
    if not game.is_over and (game.is_win() or choose_direction(game, stagnation) is None):
        game._finish("ai", "AI 结束")
    return played
