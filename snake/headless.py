#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
snake/headless.py — 无界面模式

两个用途：

1. ``python main.py demo``：用内置 AI 自动玩一局，并在终端里实时打印棋盘。
   适合在不方便开窗口的环境里确认游戏逻辑正常，也适合录 GIF。
2. 被测试代码复用：``render_board()`` 可以断言棋盘内容。
"""

from __future__ import annotations

import sys
import time

from .core import Direction, GameConfig, SnakeGame, ai_autoplay, choose_direction

# 棋盘字符
_CH = {
    "empty": "·",
    "snake": "█",
    "head": "◆",
    "food": "●",
}
_ASCII = {
    "empty": ".",
    "snake": "o",
    "head": "O",
    "food": "*",
}


def _supports_unicode() -> bool:
    """当前标准输出能否安全打印 Unicode 方块。"""
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "")
    return encoding in ("utf8", "utf16", "utf32", "utf_8")


def render_board(game: SnakeGame, *, ascii_only: bool = False, border: bool = True) -> str:
    """
    把当前棋盘渲染成多行字符串。

    :param ascii_only: 强制使用 ASCII 字符（测试时更稳定）
    :param border:     是否绘制外框
    """
    chars = _ASCII if ascii_only else _CH
    cfg = game.config

    body = set(game.snake[1:])
    head = game.head

    lines: list[str] = []
    if border:
        lines.append("+" + "-" * cfg.width + "+")

    for y in range(cfg.height):
        row: list[str] = []
        for x in range(cfg.width):
            pos = (x, y)
            if pos == head:
                row.append(chars["head"])
            elif pos == game.food:
                row.append(chars["food"])
            elif pos in body:
                row.append(chars["snake"])
            else:
                row.append(chars["empty"])
        line = "".join(row)
        lines.append(f"|{line}|" if border else line)

    if border:
        lines.append("+" + "-" * cfg.width + "+")

    status = (
        f"得分 {game.score} | 等级 {game.level} | 长度 {game.length} | "
        f"第 {game.ticks} 帧 | 状态 {game.state}"
    )
    lines.append(status)
    return "\n".join(lines)


def demo(
    config: GameConfig | None = None,
    *,
    seed: int | None = 2026,
    max_ticks: int = 4000,
    fps: float = 20.0,
    realtime: bool = True,
) -> SnakeGame:
    """
    AI 自动演示一局。

    :param realtime: True 时按 ``fps`` 实时刷新；False 时直接跑完只打印最终盘面
    :return: 跑完的 ``SnakeGame`` 实例（测试可直接检查其状态）
    """
    game = SnakeGame(config, seed=seed)
    unicode_ok = _supports_unicode()
    delay = 1.0 / fps if fps > 0 else 0.0

    # 先把棋盘画出来
    def paint() -> None:
        if realtime:
            # 光标回左上角重绘，避免滚动
            sys.stdout.write("\033[H\033[J")
            sys.stdout.write(render_board(game, ascii_only=not unicode_ok))
            sys.stdout.write("\n")
            sys.stdout.flush()

    if realtime:
        print("AI 自动演示中（Ctrl+C 可中断）…\n")

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
        if realtime:
            paint()
            if delay:
                time.sleep(delay)

    # 让状态收敛到「结束」
    if not game.is_over and (game.is_win() or choose_direction(game, stagnation) is None):
        game._finish("ai", "AI 结束")

    if realtime:
        paint()
    else:
        print(render_board(game, ascii_only=not unicode_ok))

    reason = {
        "wall": "撞墙",
        "self": "咬到自己",
        "win": "铺满棋盘，通关！",
        "ai": "AI 无路可走",
    }.get(game.death_reason or "", "未知")

    print(
        f"\n演示结束：{reason}\n"
        f"  得分 {game.score}｜等级 {game.level}｜长度 {game.length}｜"
        f"吃到 {game.foods_eaten} 个食物｜共 {game.ticks} 帧"
    )
    return game


def simulate(
    config: GameConfig | None = None,
    *,
    seed: int | None = 42,
    max_ticks: int = 2000,
) -> SnakeGame:
    """
    静默跑完一局（不打印任何东西），供基准/测试使用。
    """
    game = SnakeGame(config, seed=seed)
    ai_autoplay(game, max_ticks=max_ticks)
    return game


# 允许 `python -m snake.headless`
if __name__ == "__main__":  # pragma: no cover
    demo()
