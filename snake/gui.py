#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
snake/gui.py — 贪吃蛇图形界面版（tkinter）

tkinter 是 Python 标准库自带的，**不需要 pip 安装任何东西**。

界面结构::

    ┌────────────────────────────┐
    │  得分 120   等级 3   最高 340 │   ← 顶部信息栏
    ├────────────────────────────┤
    │                            │
    │        棋盘（格子）          │
    │                            │
    ├────────────────────────────┤
    │  空格暂停 · R 重开 · Q 退出   │   ← 底部提示
    └────────────────────────────┘

计时方式：不用 sleep 阻塞主线程，而是用 ``widget.after(ms, callback)``
把自己重新排进 Tk 事件循环 —— 这是 tkinter 里做游戏循环的正确做法。
"""

from __future__ import annotations

from .core import Direction, GameConfig, SnakeGame

# tkinter 是标准库自带的；万一某个精简版 Python 没带，也不让 import 失败
try:  # pragma: no cover - 取决于运行环境
    import tkinter as tk

    _TK_ERROR: str | None = None
except Exception as exc:  # pragma: no cover
    tk = None  # type: ignore[assignment]
    _TK_ERROR = f"{type(exc).__name__}: {exc}"

# ============================================================
#  配色（深色主题）
# ============================================================

COLORS = {
    "bg": "#161b22",          # 窗口底色
    "board": "#0d1117",       # 棋盘底色
    "grid": "#1f2630",        # 网格线
    "snake": "#2ecc71",       # 蛇身
    "snake_alt": "#27ae60",   # 蛇身间色（做出鳞片感）
    "head": "#7bed9f",        # 蛇头
    "eye": "#0d1117",         # 蛇眼
    "food": "#ff4757",        # 食物
    "food_glow": "#ff6b81",   # 食物高光
    "text": "#e6edf3",        # 主文字
    "dim": "#8b949e",         # 次要文字
    "accent": "#58a6ff",      # 强调色
    "overlay": "#161b22",     # 结束遮罩
}

# 键盘按键 → 方向
_KEY_MAP = {
    "Up": Direction.UP, "Down": Direction.DOWN,
    "Left": Direction.LEFT, "Right": Direction.RIGHT,
    "w": Direction.UP, "s": Direction.DOWN,
    "a": Direction.LEFT, "d": Direction.RIGHT,
    "W": Direction.UP, "S": Direction.DOWN,
    "A": Direction.LEFT, "D": Direction.RIGHT,
    "k": Direction.UP, "j": Direction.DOWN,
    "h": Direction.LEFT, "l": Direction.RIGHT,
    "K": Direction.UP, "J": Direction.DOWN,
    "H": Direction.LEFT, "L": Direction.RIGHT,
}


class SnakeGUI:
    """tkinter 版贪吃蛇。"""

    # 布局常量
    HUD_TOP = 56        # 顶部信息栏高度
    HUD_BOTTOM = 34     # 底部提示高度
    MARGIN = 14         # 棋盘外边距

    def __init__(
        self,
        root,
        config: GameConfig | None = None,
        *,
        seed: int | None = None,
        cell_size: int = 26,
    ):
        self.root = root
        self.config = config or GameConfig()
        self.game = SnakeGame(self.config, seed=seed)
        self.cell = cell_size

        width = self.config.width * self.cell + self.MARGIN * 2
        height = (
            self.config.height * self.cell
            + self.MARGIN * 2
            + self.HUD_TOP
            + self.HUD_BOTTOM
        )

        root.title("贪吃蛇 · Snake")
        root.configure(bg=COLORS["bg"])
        root.resizable(False, False)

        # 居中显示
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 3)
        root.geometry(f"{width}x{height}+{x}+{y}")

        self.canvas = tk.Canvas(
            root,
            width=width,
            height=height,
            bg=COLORS["bg"],
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        # 绑定按键
        root.bind("<Key>", self._on_key)

        # 启动循环
        self._after_id: str | None = None
        self._overlay_ids: list[int] = []
        self.draw()
        self._schedule()

    # --------------------------------------------------------
    #  坐标换算
    # --------------------------------------------------------

    def _cell_box(self, x: int, y: int, inset: int = 2) -> tuple[int, int, int, int]:
        """把格子坐标换算成画布像素矩形，``inset`` 制造格子之间的缝隙。"""
        left = self.MARGIN + x * self.cell + inset
        top = self.HUD_TOP + self.MARGIN + y * self.cell + inset
        return left, top, left + self.cell - inset * 2, top + self.cell - inset * 2

    # --------------------------------------------------------
    #  绘制
    # --------------------------------------------------------

    def _draw_hud(self) -> None:
        """顶部信息栏 + 底部操作提示。"""
        c = self.canvas
        g = self.game

        c.create_text(
            self.MARGIN, 22,
            anchor="w", fill=COLORS["text"],
            font=("Microsoft YaHei UI", 15, "bold"),
            text=f"得分 {g.score}",
        )
        c.create_text(
            self.MARGIN + 130, 22,
            anchor="w", fill=COLORS["accent"],
            font=("Microsoft YaHei UI", 12),
            text=f"等级 {g.level}",
        )
        c.create_text(
            self.MARGIN + 220, 22,
            anchor="w", fill=COLORS["dim"],
            font=("Microsoft YaHei UI", 12),
            text=f"长度 {g.length}",
        )
        # 最高分靠右
        board_right = self.MARGIN * 2 + self.config.width * self.cell
        c.create_text(
            board_right, 22,
            anchor="e", fill=COLORS["dim"],
            font=("Microsoft YaHei UI", 12),
            text=f"最高 {g.high_score}",
        )

        # 速度进度条：直观显示当前等级的相对速度
        bar_w = self.config.width * self.cell
        bar_y = 40
        c.create_rectangle(
            self.MARGIN, bar_y, self.MARGIN + bar_w, bar_y + 5,
            fill=COLORS["grid"], outline="",
        )
        ratio = (g.level - 1) / max(1, self.config.max_level - 1)
        c.create_rectangle(
            self.MARGIN, bar_y,
            self.MARGIN + bar_w * max(0.04, ratio), bar_y + 5,
            fill=COLORS["accent"], outline="",
        )

        # 底部提示
        hint_y = self.HUD_TOP + self.MARGIN * 2 + self.config.height * self.cell + 16
        c.create_text(
            self.MARGIN, hint_y,
            anchor="w", fill=COLORS["dim"],
            font=("Microsoft YaHei UI", 10),
            text="方向键 / WASD 移动    空格 暂停    R 重开    Q 退出",
        )

    def _draw_board(self) -> None:
        """棋盘底色 + 网格线。"""
        c = self.canvas
        cfg = self.config

        left = self.MARGIN
        top = self.HUD_TOP + self.MARGIN
        right = left + cfg.width * self.cell
        bottom = top + cfg.height * self.cell

        c.create_rectangle(
            left - 2, top - 2, right + 2, bottom + 2,
            fill=COLORS["board"], outline=COLORS["grid"], width=2,
        )

        # 网格线：格子多的时候省略细线，避免视觉噪音
        if self.cell >= 18:
            for i in range(1, cfg.width):
                x = left + i * self.cell
                c.create_line(x, top, x, bottom, fill=COLORS["grid"])
            for j in range(1, cfg.height):
                y = top + j * self.cell
                c.create_line(left, y, right, y, fill=COLORS["grid"])

    def _draw_food(self) -> None:
        """食物：一颗带高光的圆。"""
        c = self.canvas
        if self.game.food is None:
            return
        x, y = self.game.food
        left, top, right, bottom = self._cell_box(x, y, inset=4)
        c.create_oval(left, top, right, bottom, fill=COLORS["food"], outline="")
        # 高光小圆，让食物看起来有体积感
        glow = max(2, (right - left) // 4)
        c.create_oval(
            left + 3, top + 3, left + 3 + glow, top + 3 + glow,
            fill=COLORS["food_glow"], outline="",
        )

    def _draw_snake(self) -> None:
        """蛇身 + 蛇头（蛇头带朝向的眼睛）。"""
        c = self.canvas
        snake = self.game.snake

        for index in range(len(snake) - 1, -1, -1):
            x, y = snake[index]
            is_head = index == 0

            if is_head:
                color = COLORS["head"]
                inset = 1
            else:
                # 隔一格换一次颜色，形成鳞片质感
                color = COLORS["snake"] if index % 2 else COLORS["snake_alt"]
                inset = 2

            left, top, right, bottom = self._cell_box(x, y, inset=inset)
            c.create_rectangle(left, top, right, bottom, fill=color, outline="")

            if is_head:
                self._draw_eyes(left, top, right, bottom)

    def _draw_eyes(self, left: int, top: int, right: int, bottom: int) -> None:
        """在蛇头上按当前朝向画两只眼睛。"""
        c = self.canvas
        w = right - left
        h = bottom - top
        r = max(2, w // 8)

        dx, dy = self.game.direction.vector
        # 眼睛整体沿朝向前移一点，看起来像在「看前面」
        cx = left + w / 2 + dx * w * 0.16
        cy = top + h / 2 + dy * h * 0.16
        # 两眼垂直于朝向分开
        ox, oy = -dy * w * 0.22, dx * h * 0.22

        for sign in (1, -1):
            ex = cx + ox * sign
            ey = cy + oy * sign
            c.create_oval(
                ex - r, ey - r, ex + r, ey + r,
                fill=COLORS["eye"], outline="",
            )

    def _draw_overlay(self) -> None:
        """开始 / 暂停 / 结束 时的半透明提示层。"""
        c = self.canvas
        g = self.game

        if g.state == SnakeGame.STATE_RUNNING:
            self._clear_overlay()
            return

        cfg = self.config
        cx = self.MARGIN + cfg.width * self.cell / 2
        cy = self.HUD_TOP + self.MARGIN + cfg.height * self.cell / 2

        self._clear_overlay()
        pad_w, pad_h = 300, 110
        self._overlay_ids.append(
            c.create_rectangle(
                cx - pad_w / 2, cy - pad_h / 2, cx + pad_w / 2, cy + pad_h / 2,
                fill=COLORS["overlay"], outline=COLORS["accent"], width=2,
            )
        )

        if g.state == SnakeGame.STATE_READY:
            title, subtitle = "准备开始", "按方向键 / WASD 出发"
        elif g.state == SnakeGame.STATE_PAUSED:
            title, subtitle = "已暂停", "按空格继续"
        else:
            reason = {
                "wall": "撞墙了",
                "self": "咬到自己了",
                "win": "铺满棋盘，通关！",
            }.get(g.death_reason or "", "游戏结束")
            title = f"游戏结束 · {reason}"
            subtitle = f"得分 {g.score}　按 R 再来一局"

        self._overlay_ids.append(
            c.create_text(
                cx, cy - 16, fill=COLORS["text"],
                font=("Microsoft YaHei UI", 17, "bold"), text=title,
            )
        )
        self._overlay_ids.append(
            c.create_text(
                cx, cy + 18, fill=COLORS["dim"],
                font=("Microsoft YaHei UI", 11), text=subtitle,
            )
        )

    def _clear_overlay(self) -> None:
        for item_id in self._overlay_ids:
            self.canvas.delete(item_id)
        self._overlay_ids.clear()

    def draw(self) -> None:
        """重绘整个画面。"""
        self.canvas.delete("all")
        self._draw_board()
        self._draw_food()
        self._draw_snake()
        self._draw_hud()
        self._draw_overlay()

    # --------------------------------------------------------
    #  事件
    # --------------------------------------------------------

    def _on_key(self, event) -> None:
        """键盘回调。"""
        key = event.keysym
        game = self.game

        if key in ("q", "Q", "Escape"):
            self.root.destroy()
            return

        if key in ("r", "R"):
            if game.is_over or game.state == SnakeGame.STATE_PAUSED:
                game.reset()
                self.draw()
            return

        if key in ("space", "p", "P"):
            game.toggle_pause()
            self.draw()
            return

        direction = _KEY_MAP.get(key)
        if direction is None:
            return

        was_ready = game.state == SnakeGame.STATE_READY
        if game.turn(direction):
            if was_ready or game.state != SnakeGame.STATE_RUNNING:
                self.draw()

    # --------------------------------------------------------
    #  游戏循环
    # --------------------------------------------------------

    def _schedule(self) -> None:
        """把下一次 tick 排进 Tk 事件循环。"""
        interval = self.game.tick_interval_ms
        self._after_id = self.root.after(interval, self._tick)

    def _tick(self) -> None:
        """一帧：推进逻辑 → 重绘 → 排下一帧。"""
        game = self.game

        if game.state == SnakeGame.STATE_RUNNING:
            previous_level = game.level
            game.step()
            if game.is_over or game.level != previous_level:
                self.draw()
            else:
                # 只重绘动态部分，减少闪烁
                self.canvas.delete("all")
                self._draw_board()
                self._draw_food()
                self._draw_snake()
                self._draw_hud()
        elif game.is_over:
            self.draw()
            self._after_id = None
            return

        self._schedule()

    def stop(self) -> None:
        """停止循环（供测试/嵌入其他程序使用）。"""
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None


def run_gui(
    config: GameConfig | None = None,
    *,
    seed: int | None = None,
    cell_size: int = 26,
) -> int:
    """
    启动图形界面版。

    :return: 进程退出码
    """
    if tk is None:  # pragma: no cover
        print(f"图形界面不可用：{_TK_ERROR}")
        print("  替代方案: python main.py terminal  （终端版）")
        print("            python main.py demo      （无界面 AI 演示）")
        return 1

    try:
        root = tk.Tk()
    except Exception as exc:  # pragma: no cover - 无显示环境
        print(f"无法创建窗口（可能是无显示环境）：{type(exc).__name__}: {exc}")
        print("  替代方案: python main.py demo")
        return 1

    SnakeGUI(root, config, seed=seed, cell_size=cell_size)
    root.mainloop()
    return 0
