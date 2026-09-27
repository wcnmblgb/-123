#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
贪吃蛇小游戏 —— 一个用纯标准库写成的 Python 项目。

三种形态共用同一套核心逻辑：

* ``snake.core``     纯逻辑状态机（零依赖，可单元测试）
* ``snake.gui``      tkinter 图形界面版
* ``snake.terminal`` curses 终端版
* ``snake.headless`` 无界面版（内置 AI 自动演示 / 跑基准）
"""

from .core import (
    Direction,
    GameConfig,
    GameOverError,
    SnakeError,
    SnakeGame,
    StepResult,
    ai_autoplay,
    choose_direction,
)

__version__ = "1.0.0"
__all__ = [
    "Direction",
    "GameConfig",
    "GameOverError",
    "SnakeError",
    "SnakeGame",
    "StepResult",
    "ai_autoplay",
    "choose_direction",
    "__version__",
]
