#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py — 贪吃蛇小游戏入口

三种玩法（默认图形界面）::

    python main.py                       # 图形界面版
    python main.py gui                   # 同上，显式指定
    python main.py terminal              # 终端版（需要 windows-curses）
    python main.py demo                  # 无界面，AI 自动演示（看不到窗口时用这个）
    python main.py demo --no-realtime    # 直接跑完，只打印最终盘面

常用参数::

    --width 30 --height 20     改棋盘大小
    --speed 10                 初始速度（格/秒）
    --max-speed 25             满级速度
    --wrap                     开启穿墙模式（默认撞墙即死）
    --seed 42                  固定随机种子，食物序列可复现
"""

from __future__ import annotations

import argparse
import sys

from snake import __version__
from snake.core import GameConfig

# ------------------------------------------------------------
#  命令行参数
# ------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """构造 argparse 解析器。"""
    parser = argparse.ArgumentParser(
        prog="snake",
        description="贪吃蛇小游戏 —— 纯标准库实现（图形界面 / 终端 / 无界面）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python main.py                          # 打开图形界面开始玩\n"
            "  python main.py --wrap --width 30        # 穿墙模式 + 更宽的棋盘\n"
            "  python main.py terminal                 # 在终端里玩\n"
            "  python main.py demo --no-realtime       # 让 AI 快速跑完一局并打印结果\n"
            "  python main.py selftest                 # 跑一遍单元测试\n"
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"snake {__version__}",
    )

    sub = parser.add_subparsers(dest="command", help="运行模式")

    def add_common(p: argparse.ArgumentParser) -> None:
        """给子命令加上共享的配置参数。"""
        p.add_argument("--width", type=int, default=24, help="棋盘宽度（格），默认 24")
        p.add_argument("--height", type=int, default=20, help="棋盘高度（格），默认 20")
        p.add_argument("--start-length", type=int, default=3, help="初始蛇长，默认 3")
        p.add_argument("--speed", type=float, default=6.0, help="初始速度（格/秒），默认 6")
        p.add_argument("--max-speed", type=float, default=18.0, help="满级速度（格/秒），默认 18")
        p.add_argument("--wrap", action="store_true", help="穿墙模式：从另一侧出现，而不是撞死")
        p.add_argument("--seed", type=int, default=None, help="随机种子（固定食物序列）")
        p.add_argument("--max-level", type=int, default=10, help="等级上限，默认 10")

    p_gui = sub.add_parser("gui", help="图形界面版（tkinter）")
    add_common(p_gui)
    p_gui.add_argument("--cell", type=int, default=26, help="每格像素大小，默认 26")

    p_term = sub.add_parser("terminal", help="终端版（curses）")
    add_common(p_term)

    p_demo = sub.add_parser("demo", help="无界面版：AI 自动演示")
    add_common(p_demo)
    p_demo.add_argument("--max-ticks", type=int, default=2000, help="最多跑多少帧，默认 2000")
    p_demo.add_argument("--fps", type=float, default=25.0, help="演示刷新速度，默认 25")
    p_demo.add_argument("--no-realtime", action="store_true", help="直接跑完，只打印最终盘面")

    sub.add_parser("selftest", help="运行内置单元测试（tests.py）")

    return parser


def config_from_args(args: argparse.Namespace) -> GameConfig:
    """把命令行参数转成 ``GameConfig``，并做一次友好校验。"""
    try:
        return GameConfig(
            width=args.width,
            height=args.height,
            start_length=args.start_length,
            wrap=args.wrap,
            base_ticks=args.speed,
            max_ticks=args.max_speed,
            max_level=args.max_level,
        )
    except ValueError as exc:
        print(f"参数不合法：{exc}")
        sys.exit(2)


# ------------------------------------------------------------
#  各模式入口
# ------------------------------------------------------------


def run_selftest() -> int:
    """运行 tests.py 里的单元测试。"""
    import unittest

    try:
        import tests
    except ImportError:
        print("找不到 tests.py，请在项目根目录运行。")
        return 1

    suite = unittest.defaultTestLoader.loadTestsFromModule(tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def main(argv: list[str] | None = None) -> int:
    """程序主入口。"""
    parser = build_parser()
    args = parser.parse_args(argv)

    # 没给子命令 → 默认开图形界面
    command = args.command or "gui"

    if command == "selftest":
        return run_selftest()

    config = config_from_args(args)

    if command == "gui":
        from snake.gui import run_gui

        return run_gui(config, seed=args.seed, cell_size=args.cell)

    if command == "terminal":
        from snake.terminal import run_terminal

        return run_terminal(config)

    if command == "demo":
        from snake.headless import demo

        demo(
            config,
            seed=args.seed if args.seed is not None else 2026,
            max_ticks=args.max_ticks,
            fps=args.fps,
            realtime=not args.no_realtime,
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
