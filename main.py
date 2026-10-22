"""ClipVault 入口:组装存储/监听/面板/热键/托盘,跑 tk 主循环。

线程模型:tk 主循环在主线程;监听线程、keyboard 钩子线程、pystray 线程
一律通过 root.after(0, fn) 把 UI 操作编组回主线程。
"""
from __future__ import annotations

import ctypes
import os
import tkinter as tk

import keyboard
import win32gui

import clipboard_io
import config
import i18n
import win32process
from i18n import t
from hotkeys import HotkeyManager
from monitor import ClipboardMonitor
from panel import HistoryPanel
from storage import ClipItem, HistoryStorage
from tray import start_tray


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(config.APP_NAME)
        # Tk 缩放统一按真实 DPI 换算:原生控件(Entry/Text/对话框)的字号与间距才不走样
        try:
            self.root.tk.call("tk", "scaling", self.root.winfo_fpixels("1i") / 72.0)
        except Exception:
            pass

        self.storage = HistoryStorage()
        self.storage.load()
        i18n.set_lang(config.load_settings()["language"])   # 启动即应用界面语言
        self.monitor = ClipboardMonitor(self._on_clipboard_new)
        self.panel = HistoryPanel(self.root, self)
        self.prev_hwnd = None
        self.tray_icon = None
        self.hotkeys = None

    # ---- 生命周期 ----
    def run(self):
        self.monitor.start()
        self.hotkeys = HotkeyManager(
            on_toggle_panel=lambda: self.root.after(0, self.toggle_panel),
            on_paste_latest=lambda: self.root.after(0, self.paste_latest),
        )
        self.tray_icon = start_tray(self)
        self.root.mainloop()

    def quit_app(self):
        self.monitor.stop()
        self.storage.flush()   # 退出前把防抖中的写入落盘
        if self.hotkeys:
            self.hotkeys.stop()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.after(200, self.root.destroy)

    # ---- 剪贴板监听回调(监听线程) ----
    def _on_clipboard_new(self, data: dict):
        try:
            if data["kind"] == "text":
                text = data["text"]
                if len(text.encode("utf-8")) > config.MAX_TEXT_BYTES:
                    text = text[: config.MAX_TEXT_BYTES // 2]  # 超长截断(放行+标记)
                item = ClipItem(kind="text", text=text, content_hash=clipboard_io.md5(text))
            elif data["kind"] == "image":
                try:
                    fname = self.storage.save_image(data["png"])
                except ValueError:
                    return  # 超 50MB 拒绝入队
                try:
                    from PIL import Image
                    import io
                    w, h = Image.open(io.BytesIO(data["png"])).size
                    label = f"{w}×{h}"
                except Exception:
                    label = ""
                item = ClipItem(kind="image", image_file=fname, content_hash=data["hash"],
                                text=label)
            elif data["kind"] == "files":
                item = ClipItem(kind="files", files=data["files"],
                                content_hash=clipboard_io.md5("|".join(data["files"])))
            else:
                return
            self.storage.add(item)
            if self.panel.is_visible():
                self.root.after(0, self.panel.refresh)
        except Exception:
            pass  # 单条失败不拖垮监听循环

    # ---- 面板与粘贴 ----
    def toggle_panel(self):
        if self.panel.is_visible():
            self.panel.hide()
        else:
            try:
                self.prev_hwnd = win32gui.GetForegroundWindow()
            except Exception:
                self.prev_hwnd = None
            anchor = _caret_anchor()
            if anchor:
                # 优先出现在插入光标下方;下方放不下则翻到光标上方
                gap = self.panel.px(8)
                panel_h = self.panel.px(self.panel._panel_h)
                screen_h = self.root.winfo_screenheight()
                y = anchor[1] + gap
                if y + panel_h > screen_h:
                    y = anchor[1] - panel_h - gap
                self.panel.show_at(anchor[0], y)
            else:
                self.panel.show_at()

    def paste_latest(self):
        item = self.storage.latest()
        if item:
            self.paste_item(item)

    def paste_item(self, item: ClipItem):
        """写回剪贴板 → 还原焦点 → 模拟 Ctrl+V。

        粘贴后是否隐藏面板由设置决定:保持打开时,面板不抢焦点,
        Ctrl+V 仍发往前台目标窗口,可继续点选下一条。
        """
        was_visible = self.panel.is_visible()
        hide = bool(self.panel.hide_after_paste)
        if was_visible and hide:
            self.panel.hide()
        self.monitor.note_own_write()
        ok = clipboard_io.write_item(
            item.kind,
            text=item.text,
            image_path=os.path.join(config.IMAGE_DIR, item.image_file),
            files=item.files,
        )
        if not ok:
            self.monitor.cancel_own_write()
            return
        if was_visible:
            self._restore_focus()
        self.root.after(150, lambda: keyboard.send("ctrl+v"))

    def _restore_focus(self):
        if not self.prev_hwnd:
            return
        try:
            win32gui.SetForegroundWindow(self.prev_hwnd)
        except Exception:
            pass  # 目标窗口可能已关闭;Ctrl+V 落到当前焦点窗口

    def clear_all(self, confirm: bool = True):
        # 面板内按钮已弹过确认框;托盘入口在此处确认
        if confirm:
            from tkinter import messagebox
            if not messagebox.askyesno(t("confirm_title"), t("confirm_body")):
                return
        self.storage.clear()

    def clear_from_tray(self):
        self.clear_all(confirm=True)
        if self.panel.is_visible():
            self.panel.refresh()

    def on_language_changed(self):
        """语言切换:面板文案 + 托盘菜单一起刷新。"""
        self.panel.retranslate()
        self.rebuild_tray()

    def rebuild_tray(self):
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.tray_icon = start_tray(self)


def _caret_anchor() -> tuple[int, int] | None:
    """取当前前台窗口的插入光标位置(屏幕坐标)。

    优先用 GetGUIThreadInfo 拿真实 caret(输入框里的竖线位置);
    非编辑场景(桌面、资源管理器)没有 caret,退回鼠标位置。
    """
    try:
        hwnd = win32gui.GetForegroundWindow()
        tid, _ = win32process.GetWindowThreadProcessId(hwnd)
        info = win32gui.GetGUIThreadInfo(tid)
        rc = info.get("rcCaret") if info else None
        caret_hwnd = info.get("hwndCaret") if info else None
        if rc and caret_hwnd:
            x, y = win32gui.ClientToScreen(caret_hwnd, (rc[0], rc[1]))
            return x, y + max(0, rc[3] - rc[1])
    except Exception:
        pass
    try:
        return win32gui.GetCursorPos()
    except Exception:
        return None


def _enable_dpi_awareness():
    """声明进程 DPI 感知。

    不做这一步时,Windows 在 125%/150% 缩放下会把整个窗口按位图拉伸,
    字体会整体发虚;声明后由程序自己按 DPI 换算尺寸,字形保持锐利。
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


if __name__ == "__main__":
    _enable_dpi_awareness()
    App().run()
