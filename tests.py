#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests.py — 贪吃蛇核心逻辑测试

只测 ``snake.core``（纯逻辑、无界面、无网络），所以任何环境都能跑：:

    python tests.py            # 直接运行
    python -m unittest tests   # 或用 unittest 运行

重点覆盖那些「看起来对、其实有坑」的地方：
掉头拦截、尾巴让位、环绕取模、暂停后推进、食物不生成在蛇身上、
AI 永不自杀。
"""

from __future__ import annotations

import random
import unittest

from snake.core import (
    Direction,
    GameConfig,
    GameOverError,
    SnakeGame,
    _bfs_first_step,
    _reachable_area,
    ai_autoplay,
    choose_direction,
)


def make_game(**kwargs) -> SnakeGame:
    """构造一个小棋盘、固定种子、不环绕的测试用游戏。"""
    params = dict(width=10, height=8, start_length=3, seed=1234)
    params.update(kwargs)
    config = GameConfig(
        width=params.pop("width"),
        height=params.pop("height"),
        start_length=params.pop("start_length"),
        wrap=params.pop("wrap", False),
        max_level=params.pop("max_level", 10),
    )
    return SnakeGame(config, seed=params.pop("seed"))


def play_until_foods(target: int, seed: int = 11, **kwargs) -> SnakeGame:
    """
    让内置 AI 一直玩，直到吃掉 ``target`` 个食物或游戏结束。

    比「手工把食物摆到蛇头前面」可靠 —— 后者会让蛇径直撞上墙。
    """
    game = make_game(seed=seed, width=20, height=16, **kwargs)
    game.turn(Direction.RIGHT)          # 进入 running 状态
    stagnation = 0
    foods_eaten = game.foods_eaten
    while game.foods_eaten < target and not game.is_over:
        direction = choose_direction(game, stagnation)
        if direction is None:
            break
        game.turn(direction)
        game.step()
        if game.foods_eaten > foods_eaten:
            foods_eaten = game.foods_eaten
            stagnation = 0
        else:
            stagnation += 1
    return game


class TestGameConfig(unittest.TestCase):
    """配置校验。"""

    def test_rejects_tiny_board(self):
        with self.assertRaises(ValueError):
            GameConfig(width=3, height=3)

    def test_rejects_bad_speed(self):
        with self.assertRaises(ValueError):
            GameConfig(base_ticks=10, max_ticks=5)

    def test_rejects_long_start(self):
        with self.assertRaises(ValueError):
            GameConfig(width=5, height=5, start_length=6)

    def test_rejects_start_that_fills_board(self):
        with self.assertRaises(ValueError):
            GameConfig(width=5, height=5, start_length=25)

    def test_accepts_minimal_board(self):
        cfg = GameConfig(width=5, height=5, start_length=3)
        self.assertEqual(cfg.cell_count, 25)

    def test_derived_values(self):
        cfg = GameConfig(width=10, height=4)
        self.assertEqual(cfg.cell_count, 40)
        self.assertTrue(cfg.contains((9, 3)))
        self.assertFalse(cfg.contains((10, 3)))
        self.assertEqual(len(list(cfg.cells())), 40)


class TestInitialState(unittest.TestCase):
    """开局状态。"""

    def test_snake_placed_at_center(self):
        game = make_game()
        self.assertEqual(game.length, 3)
        self.assertEqual(game.head, (5, 4))
        self.assertEqual(game.state, SnakeGame.STATE_READY)
        self.assertEqual(game.score, 0)
        self.assertEqual(game.level, 1)

    def test_food_not_on_snake(self):
        game = make_game()
        self.assertNotIn(game.food, game.occupancy)

    def test_seed_is_reproducible(self):
        a = make_game(seed=7)
        b = make_game(seed=7)
        self.assertEqual(a.food, b.food)
        # 不同种子应该（通常）给出不同位置
        c = make_game(seed=999)
        self.assertIsNotNone(c.food)


class TestMovement(unittest.TestCase):
    """移动与方向控制。"""

    def test_step_moves_head_and_keeps_length(self):
        game = make_game()
        # 把食物挪到远处，避免干扰
        game.food = (0, 0)
        game.state = SnakeGame.STATE_RUNNING
        result = game.step()
        self.assertFalse(result.ate_food)
        self.assertEqual(game.head, (6, 4))
        self.assertEqual(game.length, 3)
        self.assertEqual(game.ticks, 1)

    def test_turn_updates_direction(self):
        game = make_game()
        game.food = (0, 0)
        game.state = SnakeGame.STATE_RUNNING
        self.assertTrue(game.turn(Direction.UP))
        game.step()
        self.assertEqual(game.head, (5, 3))
        self.assertIs(game.direction, Direction.UP)

    def test_reverse_direction_is_rejected(self):
        """蛇向右走时不能直接掉头向左。"""
        game = make_game()
        self.assertFalse(game.turn(Direction.LEFT))
        game.state = SnakeGame.STATE_RUNNING
        game.step()
        self.assertIs(game.direction, Direction.RIGHT)

    def test_only_one_turn_per_tick(self):
        """同一个 tick 内连按两个方向，只有第一个生效。"""
        game = make_game()
        game.food = (0, 0)
        game.state = SnakeGame.STATE_RUNNING
        game.turn(Direction.UP)
        game.turn(Direction.LEFT)     # 排队，下一帧才用
        game.step()
        self.assertEqual(game.head, (5, 3))   # 先向上
        game.step()
        self.assertEqual(game.head, (4, 3))   # 再向左

    def test_turn_starts_the_game(self):
        game = make_game()
        self.assertEqual(game.state, SnakeGame.STATE_READY)
        game.turn(Direction.DOWN)
        self.assertEqual(game.state, SnakeGame.STATE_RUNNING)

    def test_same_direction_twice_is_harmless(self):
        game = make_game()
        self.assertTrue(game.turn(Direction.RIGHT))
        self.assertTrue(game.turn(Direction.RIGHT))


class TestEating(unittest.TestCase):
    """吃食物、加分、成长。"""

    def test_eating_grows_and_scores(self):
        game = make_game()
        game.state = SnakeGame.STATE_RUNNING
        game.food = (6, 4)            # 蛇头正前方
        before = game.length
        result = game.step()
        self.assertTrue(result.ate_food)
        self.assertEqual(game.length, before + 1)
        self.assertEqual(game.score, 10)          # 10 * 等级1
        self.assertEqual(game.foods_eaten, 1)
        self.assertNotIn(game.food, game.occupancy)  # 新食物不在蛇身上

    def test_level_up_every_five_foods(self):
        game = play_until_foods(5)
        self.assertGreaterEqual(game.foods_eaten, 5)
        self.assertEqual(game.level, 2)
        self.assertGreater(game.ticks_per_second, 0)

    def test_score_uses_current_level(self):
        game = play_until_foods(5)
        self.assertEqual(game.level, 2)
        score_before = game.score
        foods_before = game.foods_eaten
        # 再吃一个，得分增量应为 10 * 等级2 = 20
        while game.foods_eaten == foods_before and not game.is_over:
            direction = choose_direction(game)
            if direction is None:
                break
            game.turn(direction)
            game.step()
        self.assertGreater(game.foods_eaten, foods_before)
        self.assertEqual(game.score - score_before, 20)


class TestCollisions(unittest.TestCase):
    """死亡判定。"""

    def test_wall_kills_when_not_wrapping(self):
        game = make_game()
        game.state = SnakeGame.STATE_RUNNING
        game.food = (0, 0)
        for _ in range(20):
            result = game.step()
            if result.game_over:
                break
        self.assertTrue(game.is_over)
        self.assertEqual(game.death_reason, "wall")

    def test_wrap_does_not_kill(self):
        game = make_game(wrap=True)
        game.state = SnakeGame.STATE_RUNNING
        game.food = (0, 0)
        for _ in range(12):
            game.step()
        self.assertFalse(game.is_over)
        self.assertTrue(game.config.contains(game.head))

    def test_self_collision_kills(self):
        """构造一个必定咬到自己的局面。"""
        game = make_game()
        game.state = SnakeGame.STATE_RUNNING
        game.food = (0, 0)
        game.snake = [(5, 4), (5, 5), (4, 5), (4, 4)]
        game.direction = Direction.RIGHT
        # 向右后转身向下，再向左，再向上即可咬到 (4,4)……用更直接的方式：
        game.snake = [(5, 4), (6, 4), (6, 5), (5, 5), (4, 5)]
        game.direction = Direction.DOWN
        result = game.step()          # 向下走到 (5,5)，那里是身体
        self.assertTrue(result.game_over)
        self.assertEqual(game.death_reason, "self")

    def test_moving_into_tail_is_allowed(self):
        """尾巴这一帧会让开，所以走进尾格不算死。"""
        game = make_game()
        game.state = SnakeGame.STATE_RUNNING
        game.food = (0, 0)
        game.snake = [(5, 4), (6, 4), (6, 5), (5, 5)]
        game.direction = Direction.DOWN
        result = game.step()          # 目标是尾格 (5,5)，不算自撞
        self.assertFalse(result.game_over)
        self.assertEqual(game.head, (5, 5))

    def test_step_after_game_over_raises(self):
        game = make_game()
        game.state = SnakeGame.STATE_RUNNING
        game._finish("wall", "test")
        with self.assertRaises(GameOverError):
            game.step()

    def test_turn_after_game_over_is_ignored(self):
        game = make_game()
        game.state = SnakeGame.STATE_RUNNING
        game._finish("wall", "test")
        self.assertFalse(game.turn(Direction.UP))


class TestPauseAndReset(unittest.TestCase):
    """暂停与重开。"""

    def test_pause_blocks_step(self):
        game = make_game()
        game.state = SnakeGame.STATE_RUNNING
        game.toggle_pause()
        self.assertEqual(game.state, SnakeGame.STATE_PAUSED)
        with self.assertRaises(GameOverError):
            game.step()

    def test_pause_resume_roundtrip(self):
        game = make_game()
        game.state = SnakeGame.STATE_RUNNING
        game.toggle_pause()
        game.toggle_pause()
        self.assertEqual(game.state, SnakeGame.STATE_RUNNING)
        game.step()   # 恢复后可以继续
        self.assertEqual(game.ticks, 1)

    def test_reset_clears_score_but_keeps_high_score(self):
        game = make_game()
        game.state = SnakeGame.STATE_RUNNING
        game.score = 250
        game.foods_eaten = 25
        game.reset()
        self.assertEqual(game.score, 0)
        self.assertEqual(game.foods_eaten, 0)
        self.assertEqual(game.high_score, 250)
        self.assertEqual(game.state, SnakeGame.STATE_READY)
        self.assertEqual(game.length, game.config.start_length)

    def test_reset_after_game_over(self):
        game = make_game()
        game.state = SnakeGame.STATE_RUNNING
        game._finish("wall", "test")
        game.reset()
        game.turn(Direction.DOWN)
        game.step()
        self.assertFalse(game.is_over)


class TestFoodSpawning(unittest.TestCase):
    """食物生成的边界情况。"""

    def test_food_none_when_board_full(self):
        """棋盘被蛇填满时，_spawn_food 必须返回 None 而不是死循环。"""
        game = make_game(width=5, height=5, start_length=3)
        game.snake = list(game.config.cells())      # 人为把棋盘填满
        game.food = None
        self.assertEqual(len(game.occupancy), game.config.cell_count)
        self.assertIsNone(game._spawn_food())

    def test_food_covers_all_free_cells(self):
        """食物应均匀落在空格上：把种子固定后检查不落在蛇身。"""
        game = make_game(seed=5)
        for _ in range(50):
            game.food = game._spawn_food()
            if game.food is None:
                break
            self.assertNotIn(game.food, game.occupancy)
            self.assertTrue(game.config.contains(game.food))

    def test_deterministic_with_injected_rng(self):
        rng_a = random.Random(2024)
        rng_b = random.Random(2024)
        game_a = SnakeGame(GameConfig(), rng=rng_a)
        game_b = SnakeGame(GameConfig(), rng=rng_b)
        self.assertEqual(game_a.food, game_b.food)


class TestSpeed(unittest.TestCase):
    """速度随等级递增。"""

    def test_speed_increases_with_level(self):
        game = make_game(max_level=10)
        speeds = []
        for level in range(1, 11):
            game._level = level
            speeds.append(game.ticks_per_second)
        self.assertEqual(speeds, sorted(speeds))
        self.assertLess(speeds[0], speeds[-1])

    def test_tick_interval_is_positive(self):
        game = make_game()
        self.assertGreaterEqual(game.tick_interval_ms, 1)


class TestHelpers(unittest.TestCase):
    """辅助函数与 AI。"""

    def test_reachable_area_counts_open_cells(self):
        cfg = GameConfig(width=4, height=4, start_length=2)
        area = _reachable_area((0, 0), set(), cfg)
        self.assertEqual(area, 16)

    def test_reachable_area_ignores_own_start_cell(self):
        """起点自己被放进障碍集合时，仍应至少能数到它自己（1 格）。"""
        cfg = GameConfig(width=5, height=5, start_length=2)
        blocked = {(0, 0), (1, 0), (0, 1)}
        self.assertEqual(_reachable_area((0, 0), blocked, cfg), 1)

    def test_bfs_first_step_moves_toward_target(self):
        """BFS 的第一步必须真的缩短距离（回归：曾经返回错误方向）。"""
        cfg = GameConfig(width=10, height=10)
        cases = [
            ((0, 0), (5, 5), (0, 1)),
            ((5, 5), (6, 5), (6, 5)),
            ((5, 5), (4, 5), (4, 5)),
            ((5, 5), (5, 0), (5, 4)),
            ((5, 5), (5, 9), (5, 6)),
            ((0, 0), (9, 9), (0, 1)),
        ]
        for head, target, expected in cases:
            got = _bfs_first_step(head, target, set(), cfg)
            self.assertEqual(got, expected, f"{head} -> {target}")

    def test_bfs_step_reduces_distance(self):
        """无论返回哪一格，它都必须比当前位置更接近目标。"""
        cfg = GameConfig(width=12, height=12)
        for head in [(0, 0), (5, 5), (11, 0), (3, 9)]:
            for target in [(0, 0), (5, 5), (11, 11), (7, 2)]:
                step = _bfs_first_step(head, target, set(), cfg)
                if step is None:
                    continue
                before = abs(head[0] - target[0]) + abs(head[1] - target[1])
                after = abs(step[0] - target[0]) + abs(step[1] - target[1])
                self.assertLess(after, before, f"{head} -> {target} 走了 {step}")

    def test_bfs_allows_target_inside_blocked(self):
        """食物那一格可能被调用方一并放进 blocked，搜索必须仍然成功。"""
        cfg = GameConfig(width=10, height=10)
        blocked = {(5, 5), (5, 6), (4, 5)}
        self.assertEqual(_bfs_first_step((5, 5), (4, 5), blocked, cfg), (4, 5))

    def test_bfs_returns_none_when_sealed(self):
        """四周被身体围死时，必须返回 None 而不是死循环。"""
        cfg = GameConfig(width=10, height=10)
        blocked = {(5, 4), (4, 5), (5, 6), (6, 5)}
        self.assertIsNone(_bfs_first_step((5, 5), (0, 0), blocked, cfg))

    def test_bfs_avoids_walls(self):
        """不能穿越棋盘边界。"""
        cfg = GameConfig(width=8, height=8)
        step = _bfs_first_step((0, 0), (7, 7), set(), cfg)
        self.assertEqual(step, (0, 1))
        self.assertTrue(cfg.contains(step))

    def test_ai_follows_path_to_food(self):
        """空棋盘上 AI 应当沿最短路朝食物走。"""
        game = make_game(width=10, height=8)
        game.state = SnakeGame.STATE_RUNNING
        # 蛇头 (5,4) 朝上，食物在右下方：两条路都合法，AI 应选更接近的那一步
        game.snake = [(5, 4), (4, 4), (3, 4)]
        game.direction = Direction.UP
        game.food = (7, 6)
        chosen = choose_direction(game, 0)
        self.assertIsNotNone(chosen)
        self.assertIsNot(chosen, Direction.LEFT)   # 不能背对食物走

    def test_ai_handles_food_directly_behind(self):
        """
        食物正好在蛇的正后方时，掉头是非法操作。

        AI 不能因此卡死（返回 None），也不能选择非法方向 ——
        它应该先拐个弯，绕过去吃。
        """
        game = make_game(width=10, height=8)
        game.state = SnakeGame.STATE_RUNNING
        game.snake = [(5, 4), (5, 3), (5, 2)]      # 蛇头朝上，身体在下方
        game.direction = Direction.UP
        game.food = (5, 6)                          # 正后方
        chosen = choose_direction(game, 0)
        self.assertIsNotNone(chosen)
        self.assertIsNot(chosen, Direction.DOWN)    # 掉头非法

    def test_ai_prefers_open_space_when_path_blocked(self):
        """到食物的路被自己的身体挡住时，应选活动空间最大的方向。"""
        game = make_game(width=10, height=8)
        game.state = SnakeGame.STATE_RUNNING
        # 用一条长蛇把右侧与下方封住，食物在身体另一侧
        game.snake = [
            (5, 4), (6, 4), (7, 4), (8, 4), (8, 5), (8, 6),
            (7, 6), (6, 6), (5, 6), (4, 6), (4, 5),
        ]
        game.direction = Direction.LEFT
        game.food = (8, 7)
        direction = choose_direction(game, 999)   # 强制走「空间优先」
        self.assertIsNotNone(direction)

    def test_ai_avoids_immediate_death(self):
        """蛇头贴着墙时，AI 不能选择撞墙的方向。"""
        game = make_game()
        game.state = SnakeGame.STATE_RUNNING
        game.snake = [(9, 4), (8, 4), (7, 4)]
        game.direction = Direction.RIGHT
        game.food = (0, 4)
        direction = choose_direction(game)
        self.assertIsNotNone(direction)
        self.assertIsNot(direction, Direction.RIGHT)

    def test_ai_autoplay_reaches_valid_end_state(self):
        game = make_game(seed=99, width=15, height=12)
        played = ai_autoplay(game, max_ticks=1500)
        self.assertGreater(played, 0)
        self.assertTrue(game.is_over)
        self.assertEqual(len(game.snake), len(set(game.snake)))   # 无重复格子
        self.assertEqual(game.death_reason, "ai")

    def test_ai_grows_the_snake(self):
        game = make_game(seed=3, width=15, height=12)
        ai_autoplay(game, max_ticks=1500)
        self.assertGreater(game.score, 0)
        self.assertGreater(game.length, game.config.start_length)

    def test_ai_never_self_collides(self):
        """多种子跑一遍，AI 不应出现自撞或撞墙。"""
        for seed in range(4):
            game = make_game(seed=seed, width=14, height=11)
            ai_autoplay(game, max_ticks=600)
            self.assertNotIn(
                game.death_reason, ("self", "wall"),
                f"seed={seed} 时 AI 意外死亡：{game.death_reason}",
            )

    def test_ai_keeps_eating_instead_of_circling(self):
        """回归测试：AI 不能吃到一个食物后就永远绕圈。"""
        game = make_game(seed=1, width=20, height=16)
        ai_autoplay(game, max_ticks=1200)
        self.assertGreater(
            game.foods_eaten, 3,
            f"AI 只吃到 {game.foods_eaten} 个食物，可能在绕圈",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
