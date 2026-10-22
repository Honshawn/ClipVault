"""系统托盘:图标 + 右键菜单(显示面板/粘贴最新/清空历史/退出)。"""
from __future__ import annotations

import threading

import pystray
from PIL import Image, ImageDraw

import config
from i18n import t


def _make_icon() -> Image.Image:
    """程序内生成 64x64 图标:蓝色圆角底 + 白色剪贴板造型,无需外部资源文件。"""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, 62, 62], radius=14, fill="#0078d7")
    d.rounded_rectangle([18, 14, 46, 54], radius=4, fill="#ffffff")
    d.rounded_rectangle([24, 10, 40, 20], radius=3, fill="#ffffff")
    d.rectangle([22, 28, 42, 30], fill="#9dc3e6")
    d.rectangle([22, 36, 42, 38], fill="#9dc3e6")
    d.rectangle([22, 44, 36, 46], fill="#9dc3e6")
    return img


def start_tray(app) -> pystray.Icon:
    """app 需提供: root.after / toggle_panel / paste_latest / clear_all / quit_app。"""
    def in_tk(fn):
        return lambda *_: app.root.after(0, fn)

    menu = pystray.Menu(
        pystray.MenuItem(t("tray_show"), in_tk(app.toggle_panel), default=True),
        pystray.MenuItem(t("tray_paste", hotkey=config.HOTKEY_PASTE_LATEST),
                         in_tk(app.paste_latest)),
        pystray.MenuItem(t("tray_clear"), in_tk(app.clear_from_tray)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t("tray_quit"), in_tk(app.quit_app)),
    )
    icon = pystray.Icon(config.APP_NAME, _make_icon(), t("tray_tip"), menu)
    threading.Thread(target=icon.run, daemon=True, name="TrayIcon").start()
    return icon
