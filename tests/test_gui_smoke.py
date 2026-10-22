"""GUI 冒烟:面板可创建、可填充、可选中、可隐藏;main.App 可组装。
运行: python tests/test_gui_smoke.py
"""
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import i18n

_tmp = tempfile.mkdtemp(prefix="clipvault_gui_")
config.DATA_DIR = _tmp
config.HISTORY_FILE = os.path.join(_tmp, "history.json")
config.IMAGE_DIR = os.path.join(_tmp, "images")
config.SETTINGS_FILE = os.path.join(_tmp, "settings.json")

passed = 0


def check(name, cond):
    global passed
    assert cond, f"FAIL: {name}"
    passed += 1
    print(f"  PASS {name}")


import keyboard

keyboard.send = lambda *a, **k: None   # 测试中禁止真实发送 Ctrl+V

from main import App
from storage import ClipItem

app = App()
long_text = "长文本第一行\n" + "第二行完整内容 " * 10
app.storage.add(ClipItem(kind="text", text="第一条文本", content_hash="a"))
app.storage.add(ClipItem(kind="text", text="第二条 text", content_hash="b"))
app.storage.add(ClipItem(kind="files", files=["C:/x.txt"], content_hash="c"))

app.panel.show()
app.root.update_idletasks()
check("面板: show 后可见", app.panel.is_visible())
check("面板: 列表填充 3 行", app.panel.row_count() == 3)
check("面板: 默认选中最新一条", app.panel.selected_item().content_hash == "c")
check("详情: 选中后详情区可见", app.panel.detail.winfo_ismapped())
check("详情: 文件条目显示全路径", "C:/x.txt" in app.panel.detail_text.get("1.0", "end"))
check("详情: 缺失文件标注", "不存在" in app.panel.detail_text.get("1.0", "end"))

# 选中文本条目 → 详情显示完整内容(不截断)
app.panel.select_index(1)
app.root.update_idletasks()
check("详情: 文本条目显示完整内容", app.panel.detail_text.get("1.0", "end-1c") == "第二条 text")

# 图片条目 → 详情区显示缩略图
from PIL import Image
import io
buf = io.BytesIO()
Image.new("RGB", (300, 200), (30, 120, 200)).save(buf, "PNG")
img_item = ClipItem(kind="image", image_file=app.storage.save_image(buf.getvalue()), content_hash="img")
app.storage.add(img_item)
app.panel.refresh()
img_idx = next(i for i, it in enumerate(app.panel._items) if it.kind == "image")
app.panel.select_index(img_idx)
app.root.update_idletasks()
check("详情: 图片条目加载缩略图", app.panel._thumb_ref is not None)
check("详情: 图片模式隐藏文本框", not app.panel.detail_text.winfo_ismapped())

# 长文本条目完整展示(换行保留,不截断)
app.storage.add(ClipItem(kind="text", text=long_text, content_hash="long"))
app.panel.refresh()
app.panel.select_index(0)
app.root.update_idletasks()
check("详情: 长文本换行完整保留", app.panel.detail_text.get("1.0", "end-1c") == long_text)

app.panel.filter_var.set("第一条")
app.panel.refresh()
check("面板: 过滤命中 1 行", app.panel.row_count() == 1)
app.panel.filter_var.set("")
app.panel.refresh()

# 键盘上下移动选择(先归零,避免受"选中项保持"逻辑影响)
app.panel.select_index(0)
app.panel.move(1)
check("键盘: 下移一行", app.panel._sel == 1)
app.panel.move(-5)
check("键盘: 上移到顶不越界", app.panel._sel == 0)
app.panel.move(99)
check("键盘: 下移到底不越界", app.panel._sel == app.panel.row_count() - 1)

# 真实按键事件:Canvas 类绑定不得吞掉方向键(回归项)
app.panel.select_index(0)
app.panel.canvas.focus_set()
app.panel.canvas.event_generate("<Down>")
app.root.update()
check("键盘事件: Canvas 上按↓能移动选中", app.panel._sel == 1)

# 详情区:拖动分隔条后高度固定并持久化
from types import SimpleNamespace
app.root.update()
check("分隔条: 位于详情区上边界",
      app.panel.splitter.winfo_y() < app.panel.detail.winfo_y())
h_before = app.panel.detail.winfo_height()
app.panel._split_start(SimpleNamespace(y_root=500))
app.panel._split_drag(SimpleNamespace(y_root=440))
app.panel._split_end(SimpleNamespace(y_root=440))
app.root.update()
check("分隔条: 上拖后详情区变高", app.panel.detail.winfo_height() > h_before)
check("分隔条: 固定高度已落盘", config.load_settings()["detail_h"] > 0)

# 设置窗口可打开、随面板隐藏一起关闭
app.panel.open_settings()
app.root.update()
check("设置: 窗口可打开", bool(app.panel._settings_win and app.panel._settings_win.winfo_exists()))
app.panel.hide()
check("设置: 随面板隐藏一起关闭", not (app.panel._settings_win and app.panel._settings_win.winfo_exists()))
app.panel.show()
app.root.update()

# 粘贴后行为:隐藏 / 保持打开两种模式
app.panel.hide_after_paste = True
app.paste_item(app.panel.selected_item())
app.root.update()
check("设置: 隐藏模式下粘贴后面板关闭", not app.panel.is_visible())

app.panel.show()
app.panel.hide_after_paste = False
app.root.update()
app.paste_item(app.panel.selected_item())
app.root.update()
check("设置: 保持模式下粘贴后面板仍打开", app.panel.is_visible())

# 面板尺寸可调并持久化
w0, h0 = app.panel._panel_w, app.panel._panel_h
app.panel._resize_start(SimpleNamespace(x_root=100, y_root=100))
app.panel._resize_drag(SimpleNamespace(x_root=160, y_root=140))
app.root.update()
app.panel._resize_end(SimpleNamespace(x_root=160, y_root=140))
check("缩放: 拖拽后面板变大", app.panel._panel_w > w0 and app.panel._panel_h > h0)
check("缩放: 尺寸已落盘", config.load_settings()["panel_w"] == app.panel._panel_w)

# 按钮点击回归:<ButtonPress>/<ButtonRelease> 必须真正触发命令
# (曾经 <Button-1> 与 <ButtonPress-1> 同事件互相覆盖,导致全部按钮失效)
def click(btn):
    btn.event_generate("<ButtonPress-1>", x=5, y=5)
    btn.event_generate("<ButtonRelease-1>", x=5, y=5)
    app.root.update()


app.panel.show()
app.root.update()
click(app.panel.btn_close)
check("按钮: 关闭点击后面板隐藏", not app.panel.is_visible())
app.panel.show()
app.root.update()
check("关闭: × 位于顶栏(列表之上)",
      app.panel.btn_close.winfo_rooty() < app.panel.canvas.winfo_rooty())


def _foot_texts(widget):
    out = []
    for w in widget.winfo_children():
        try:
            out.append(w.cget("text"))
        except Exception:
            pass
    return out


check("关闭: 底部不再有关闭按钮", "关闭" not in _foot_texts(app.panel.btn_clear.master))

app.panel.show()
app.root.update()
click(app.panel.btn_settings)
check("按钮: 设置点击后弹出设置窗",
      bool(app.panel._settings_win and app.panel._settings_win.winfo_exists()))
app.panel.hide()          # 同时销毁设置窗
app.panel.show()
app.root.update()

# 拖动标题移动面板
x0, y0 = app.panel.winfo_x(), app.panel.winfo_y()
app.panel._drag_start(SimpleNamespace(x_root=500, y_root=400))
app.panel._drag_move(SimpleNamespace(x_root=560, y_root=450))
app.root.update()
check("拖动: 标题拖拽后面板位移", (app.panel.winfo_x(), app.panel.winfo_y()) != (x0, y0))

# 设置项整合:单一"保持面板打开"开关 + 语言切换
app.panel.open_settings()
app.root.update()
check("设置: 粘贴行为整合为单项开关", hasattr(app.panel, "_keep_open_var"))
check("设置: 语言默认中文", i18n.get_lang() == "zh")
app.panel._keep_open_var.set(True)
app.panel._apply_paste_mode()
check("设置: 勾选开关后不隐藏面板", app.panel.hide_after_paste is False)
app.panel._keep_open_var.set(False)
app.panel._apply_paste_mode()
check("设置: 取消勾选后恢复隐藏", app.panel.hide_after_paste is True)

app.panel._lang_var.set("en")
app.panel._apply_language()
app.root.update()
check("语言: 切英文后标题变英文", app.panel._title.cget("text") == "Clipboard History")
check("语言: 英文已写入设置", config.load_settings()["language"] == "en")
check("语言: 按钮文案同步英文", app.panel.btn_paste.cget("text") == "Paste")
app.panel._lang_var.set("zh")
app.panel._apply_language()
app.root.update()
check("语言: 切回中文", app.panel._title.cget("text") == "剪贴板历史")
app.panel.hide()

# 空历史 → 详情区回到占位文本(放在取材之后,避免影响上面的粘贴流程用例)
app.panel.hide()
app.root.update_idletasks()
check("面板: hide 后不可见", not app.panel.is_visible())

# 模拟粘贴流程写回剪贴板(不模拟 Ctrl+V,只验证写回)
item = next(it for it in app.storage.all_newest_first() if it.text == "第二条 text")
app.monitor.note_own_write()
import clipboard_io
assert clipboard_io.write_item(item.kind, text=item.text)
data = clipboard_io.read_clipboard()
check("粘贴流程: 选中内容写回剪贴板", data and data["text"] == "第二条 text")

# 清空按钮(确认框打桩,避免阻塞)
import panel as panel_mod
panel_mod.messagebox.askyesno = lambda *a, **k: True
app.panel.show()
app.root.update()
click(app.panel.btn_clear)
check("按钮: 清空点击后历史为空", app.storage.count() == 0)
check("空态: 列表为 0 行", app.panel.row_count() == 0)
check("空态: 详情显示占位提示", "选中条目" in app.panel.detail_text.get("1.0", "end"))

# 状态栏反馈自熄(2.5s 后恢复计数)
app.panel._flash_status("已清空")
check("反馈: 状态栏显示临时文案", app.panel.status.cget("text") == "已清空")
app.panel._reset_status()
check("反馈: 自熄后恢复计数", "条" in app.panel.status.cget("text"))

# 安全回归:settings 越界值被夹紧;图片文件名只取 basename;i18n 列表不累积
import panel as panel_mod
check("校验: 非法设置回退默认", panel_mod.clamp_int("abc", 480, 2000, 620) == 620)
check("校验: 超大值被夹到上限", panel_mod.clamp_int(999999, 480, 2000, 620) == 2000)
check("校验: 负数被夹到下限", panel_mod.clamp_int(-5, 0, 400, 0) == 0)

before = len(app.panel._i18n_widgets)
for _ in range(3):
    app.panel.open_settings()
    app.root.update()
    app.panel.hide()
check("i18n: 反复开关设置窗不累积控件引用", len(app.panel._i18n_widgets) == before)

app.panel.show()
app.root.update()
app.storage.add(ClipItem(kind="image", image_file="../../evil.png", content_hash="evil"))
app.panel.refresh()
app.panel.select_index(0)
app.root.update()
check("安全: 图片路径穿越被拦截", app.panel.detail_img.cget("image") == "")

app.root.destroy()
print(f"\n全部通过: {passed} 项")
