#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
snake/terminal.py — 贪吃蛇终端版（curses）

在 Windows 上需要先安装 windows-curses：::

    pip install windows-curses

如果当前环境没有 curses，本模块不会抛异常，而是把 ``available()``
置为 False，由 cli 层给出友好提示 —— 这样「没有 curses 的机器」
也能正常使用图形界面版和无界面版。
"""

from __future__ import annotations

import sys

from .core import Direction, GameConfig, SnakeGame

# ------------------------------------------------------------
#  curses 是可选依赖：缺失时整个模块仍可被 import
# ------------------------------------------------------------

try:  # pragma: no cover - 取决于运行环境
    import curses

    _CURSES_ERROR: str | None = None
except Exception as exc:  # pragma: no cover
    curses = None  # type: ignore[assignment]
    _CURSES_ERROR = f"{type(exc).__name__}: {exc}"


def available() -> bool:
    """当前环境是否可以使用终端版。"""
    return curses is not None


def unavailable_reason() -> str:
    """返回终端版不可用的原因（可用时返回空字符串）。"""
    return _CURSES_ERROR or ""


# 按键 → 方向。同时支持方向键、WASD 与 HJKL（vim 风格）。
_KEY_TO_DIRECTION = {
    "KEY_UP": Direction.UP,
    "KEY_DOWN": Direction.DOWN,
    "KEY_LEFT": Direction.LEFT,
    "KEY_RIGHT": Direction.RIGHT,
    "w": Direction.UP,
    "s": Direction.DOWN,
    "a": Direction.LEFT,
    "d": Direction.RIGHT,
    "k": Direction.UP,
    "j": Direction.DOWN,
    "h": Direction.LEFT,
    "l": Direction.RIGHT,
}

# 方块字符与 ASCII 降级方案
_BLOCK = "■"
_FOOD = "●"
_HEAD = "◆"


def _char_safe(stdscr) -> bool:
    """检测终端能否安全输出 Unicode 方块（否则退回 ASCII）。"""
    encoding = (getattr(stdscr, "encoding", None) or sys.stdout.encoding or "").lower()
    return encoding.replace("-", "") in ("utf8", "utf16", "utf32", "utf_8")


class TerminalApp:
    """基于 curses 的贪吃蛇界面。"""

    def __init__(self, stdscr, config: GameConfig | None = None, seed: int | None = None):
        self.stdscr = stdscr
        self.game = SnakeGame(config, seed=seed)
        self.unicode_ok = _char_safe(stdscr)
        self.running = True

        curses.curs_set(0)          # 隐藏光标
        self.stdscr.nodelay(True)   # 非阻塞读键
        self.stdscr.keypad(True)    # 让方向键变成 KEY_UP 这类名字

        # 颜色：curses 的 use_default_colors 不是所有平台都有
        self.color = False
        try:
            if curses.has_colors():
                curses.start_color()
                curses.use_default_colors()
                curses.init_pair(1, curses.COLOR_GREEN, -1)   # 蛇身
                curses.init_pair(2, curses.COLOR_CYAN, -1)    # 蛇头
                curses.init_pair(3, curses.COLOR_RED, -1)     # 食物
                curses.init_pair(4, curses.COLOR_YELLOW, -1)  # 状态栏
                self.color = True
        except Exception:
            self.color = False

    # --------------------------------------------------------
    #  绘制
    # --------------------------------------------------------

    def _attr(self, pair: int, bold: bool = False) -> int:
        if not self.color:
            return curses.A_BOLD if bold else curses.A_NORMAL
        attr = curses.color_pair(pair)
        return attr | curses.A_BOLD if bold else attr

    def _char(self, unicode_char: str, ascii_char: str) -> str:
        return unicode_char if self.unicode_ok else ascii_char

    def draw(self) -> None:
        """把当前棋盘画到屏幕上。"""
        game = self.game
        cfg = game.config
        self.stdscr.erase()
        max_y, max_x = self.stdscr.getmaxyx()

        # 顶部信息栏
        title = f" 贪吃蛇 · 得分 {game.score} · 等级 {game.level} · 长度 {game.length} · 最高 {game.high_score} "
        try:
            self.stdscr.addstr(0, 0, title[: max_x - 1], self._attr(4, bold=True))
            self.stdscr.addstr(1, 0, " 方向键/WASD 移动 · 空格暂停 · R 重开 · Q 退出"[: max_x - 1])
        except curses.error:
            pass

        # 棋盘绘制起点
        board_top = 3
        board_left = 1

        # 可用空间不够时给出明确提示，而不是画出错位的图
        needed_h = board_top + cfg.height + 2
        needed_w = board_left + cfg.width * 2 + 2
        if max_y < needed_h or max_x < needed_w:
            msg = f"窗口太小：需要至少 {needed_w}x{needed_h}，当前 {max_x}x{max_y}，请放大终端"
            try:
                self.stdscr.addstr(2, 0, msg[: max_x - 1])
            except curses.error:
                pass
            self.stdscr.refresh()
            return

        # 画边框
        hline = "─" if self.unicode_ok else "-"
        vline = "│" if self.unicode_ok else "|"
        corner = {"tl": "┌", "tr": "┐", "bl": "└", "br": "┘"}
        if not self.unicode_ok:
            corner = {"tl": "+", "tr": "+", "bl": "+", "br": "+"}
        try:
            self.stdscr.addstr(board_top - 1, board_left, corner["tl"] + hline * (cfg.width * 2) + corner["tr"])
            for y in range(cfg.height):
                self.stdscr.addstr(board_top + y, board_left, vline)
                self.stdscr.addstr(board_top + y, board_left + cfg.width * 2 + 1, vline)
            self.stdscr.addstr(board_top + cfg.height, board_left, corner["bl"] + hline * (cfg.width * 2) + corner["br"])
        except curses.error:
            pass

        # 画蛇
        body_char = self._char(_BLOCK, "o")
        head_char = self._char(_HEAD, "O")
        food_char = self._char(_FOOD, "*")

        for index, (x, y) in enumerate(game.snake):
            char = head_char if index == 0 else body_char
            attr = self._attr(2, bold=True) if index == 0 else self._attr(1)
            try:
                self.stdscr.addstr(board_top + y, board_left + 1 + x * 2, char, attr)
            except curses.error:
                pass

        # 画食物
        if game.food is not None:
            fx, fy = game.food
            try:
                self.stdscr.addstr(board_top + fy, board_left + 1 + fx * 2, food_char, self._attr(3, bold=True))
            except curses.error:
                pass

        # 状态提示
        hint = ""
        if game.state == SnakeGame.STATE_READY:
            hint = "按任意方向键开始"
        elif game.state == SnakeGame.STATE_PAUSED:
            hint = "已暂停 —— 按空格继续"
        elif game.is_over:
            reason = {"wall": "撞墙", "self": "咬到自己", "win": "通关", "ai": "结束"}.get(
                game.death_reason or "", "结束"
            )
            hint = f"游戏结束（{reason}）—— 按 R 再来一局，Q 退出"
        if hint:
            try:
                self.stdscr.addstr(cfg.height + board_top + 1, 1, hint[: max_x - 2], self._attr(4, bold=True))
            except curses.error:
                pass

        self.stdscr.refresh()

    # --------------------------------------------------------
    #  主循环
    # --------------------------------------------------------

    def handle_key(self, key: int) -> None:
        """处理一个按键。"""
        game = self.game

        if key == -1:                      # 无按键
            return
        if key in (ord("q"), ord("Q"), 27):  # q / Esc
            self.running = False
            return
        if key in (ord("r"), ord("R")):
            game.reset()
            return
        if key == ord(" "):
            game.toggle_pause()
            return

        try:
            name = curses.keyname(key)
        except Exception:
            return
        if isinstance(name, bytes):
            name = name.decode("utf-8", "ignore")
        name = name.lower()

        direction = _KEY_TO_DIRECTION.get(name)
        if direction is not None:
            game.turn(direction)

    def run(self, max_ticks: int | None = None) -> None:
        """
        进入主循环。

        :param max_ticks: 只跑指定帧数就退出（自动化测试用）
        """
        from time import monotonic  # 局部导入，避免模块级副作用

        game = self.game
        last = monotonic()
        frames = 0

        while self.running:
            self.draw()

            # 计算本帧允许消耗的时间
            now = monotonic()
            interval = game.tick_interval_ms / 1000.0

            if game.state == SnakeGame.STATE_RUNNING and now - last >= interval:
                try:
                    game.step()
                except Exception:
                    pass
                last = now
                frames += 1
                if max_ticks is not None and frames >= max_ticks:
                    break
            elif game.state != SnakeGame.STATE_RUNNING:
                last = now

            # 处理按键（非阻塞）
            key = self.stdscr.getch()
            while key != -1:
                self.handle_key(key)
                key = self.stdscr.getch()

            curses.napms(16)  # 约 60 FPS 的界面刷新节奏


def run_terminal(config: GameConfig | None = None, max_ticks: int | None = None) -> int:
    """
    启动终端版（curses 包装入口）。

    :return: 进程退出码
    """
    if not available():
        print("终端版不可用：当前 Python 没有 curses 模块。")
        print(f"  平台: {sys.platform}，原因: {unavailable_reason()}")
        if sys.platform == "win32":
            print("  Windows 解决办法: pip install windows-curses")
        print("  替代方案: python main.py gui     （图形界面版）")
        print("            python main.py demo    （无界面 AI 演示）")
        return 1

    def _main(stdscr) -> None:
        TerminalApp(stdscr, config).run(max_ticks=max_ticks)

    curses.wrapper(_main)
    return 0
