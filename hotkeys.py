"""全局热键:双击 Ctrl 呼出/隐藏面板;Ctrl+Alt+V 粘贴最新一条。

双击判定:keyboard.hook 观察所有按键——两次 Ctrl 按下间隔 ≤ 阈值且中间无其他按键即触发。
按住 Ctrl 组合键(Ctrl+C 等)时,中间出现的其他按键会重置计时,不会误触发。
"""
from __future__ import annotations

import time

import keyboard

import config

_CTRL_NAMES = {"ctrl", "left ctrl", "right ctrl"}


class HotkeyManager:
    def __init__(self, on_toggle_panel, on_paste_latest):
        self.on_toggle_panel = on_toggle_panel
        self._last_ctrl_down = 0.0
        keyboard.add_hotkey(config.HOTKEY_PASTE_LATEST, on_paste_latest)
        self._hook = keyboard.hook(self._on_event)

    def _on_event(self, e):
        if e.event_type != "down":
            return
        name = (e.name or "").lower()
        if name in _CTRL_NAMES:
            now = time.monotonic()
            if 0 < self._last_ctrl_down and now - self._last_ctrl_down <= config.DOUBLE_CTRL_WINDOW:
                self._last_ctrl_down = 0.0
                try:
                    self.on_toggle_panel()
                except Exception:
                    pass
            else:
                self._last_ctrl_down = now
        else:
            self._last_ctrl_down = 0.0  # 组合键场景重置,防误触

    def stop(self):
        try:
            keyboard.unhook(self._hook)
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
