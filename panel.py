"""历史面板:纯 tkinter Canvas 自绘列表(单行卡片 + 选中详情)。

设计约定
- 配色全部来自顶部 THEME 字典,控件内不写死颜色
- 字号全部走像素单位(负数字号),避免小数像素导致字形发虚
- 间距遵守 8px 栅格(8/16/24),按 DPI 换算
- 面板尺寸、详情区高度、粘贴后行为可调,存 settings.json
- 无第三方 UI 依赖:不引入 customtkinter/Qt,包体不变
"""
from __future__ import annotations

import os
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox

from PIL import Image, ImageTk

import config
import i18n
from i18n import t

# ---- 主题:唯一颜色来源 ----
THEME = {
    "bg": "#F7F8FA",            # 页面底
    "surface": "#FFFFFF",       # 列表卡片
    "inset": "#F3F4F6",         # 详情区(内凹一档,替代边框)
    "border": "#E4E6EB",        # 发丝级描边
    "primary": "#2F6FED",
    "primary_hover": "#4C85F5",
    "primary_pressed": "#2559C4",
    "text": "#1F2329",
    "muted": "#6B7280",
    "disabled": "#B0B5BD",
    "hover": "#F0F1F4",
    "selected": "#EAF0FB",
    "success": "#22A06B",
    "warning": "#E8A33D",
    "danger": "#E5484D",
    "danger_hover": "#FDEDEE",
    "chip": {"text": "#2F6FED", "image": "#22A06B", "files": "#E8A33D"},
    "scrollbar": "#D9DDE2",
}

# 中文字体回退链:优先雅黑 UI,其次系统常见 CJK 字体
FONT_STACK = ["Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC",
              "Noto Sans CJK SC", "Segoe UI"]

MIN_W, MIN_H = 480, 420       # 面板最小逻辑尺寸
DEFAULT_W, DEFAULT_H = 620, 660
DEFAULT_DETAIL_H = 150        # 详情区自适应上限


def _pick_family(root) -> str:
    available = set(tkfont.families(root))
    for name in FONT_STACK:
        if name in available:
            return name
    return "TkDefaultFont"  # 极端兜底(常规 Windows 环境不会命中)


class HistoryPanel(tk.Toplevel):
    ROW_H = 44

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._items = []      # 过滤后的条目,下标与行号一一对应
        self._sel = -1
        self._hover = -1
        self._thumb_ref = None
        self._status_job = None   # 状态栏自熄定时器
        self._settings_win = None
        self._resize_origin = None
        self._split_origin = None
        self._drag_origin = None
        self._i18n_widgets = []   # [(widget, key)] 语言切换时统一重设文案

        # 用户设置
        s = config.load_settings()
        self._panel_w = int(s["panel_w"])
        self._panel_h = int(s["panel_h"])
        self._detail_fixed_h = int(s["detail_h"])   # 0 = 自适应
        self.hide_after_paste = bool(s["hide_after_paste"])

        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=THEME["bg"])

        # 高 DPI 缩放系数(100% = 1.0);字体用像素单位后必须自己缩放
        self._s = max(1.0, self.winfo_fpixels("1i") / 96.0)
        self.row_h = self.px(self.ROW_H)
        self.detail_h = self.px(DEFAULT_DETAIL_H)

        self._fonts = self._build_fonts()
        self._font = self._fonts["body"]
        self._font_small = self._fonts["small"]
        self._font_title = self._fonts["title"]
        self._font_num = self._fonts["num"]

        # 外框(1px 描边,弥补无边框窗口缺省外观)
        frame = tk.Frame(self, bg=THEME["bg"],
                         highlightbackground=THEME["border"], highlightthickness=1)
        frame.pack(fill="both", expand=True)
        self._frame = frame

        # ---- 顶栏:标题 + 状态 + 搜索 ----
        pad = self.px(24)
        header = tk.Frame(frame, bg=THEME["bg"])
        header.pack(side="top", fill="x", padx=pad, pady=(self.px(16), self.px(8)))
        self._title = tk.Label(header, text=t("title"), bg=THEME["bg"], fg=THEME["text"],
                               font=self._font_title, cursor="fleur")
        self._title.pack(side="left")
        self._i18n_widgets.append((self._title, "title"))

        # 右上角关闭(×):先 pack 到 right 即最靠右
        self.btn_close = self._icon_close(header)
        self.btn_close.pack(side="right", padx=(self.px(8), 0))
        # 顶栏空白处与标题均可拖动窗口
        for _w in (header, self._title):
            _w.bind("<ButtonPress-1>", self._drag_start)
            _w.bind("<B1-Motion>", self._drag_move)

        self.filter_var = tk.StringVar()
        # 聚焦双环:外环变色 + 内层 1px 留白,模拟 box-shadow 咬合(不加 outline)
        self._ring = tk.Frame(header, bg=THEME["border"])
        self._ring.pack(side="right")
        ring_inner = tk.Frame(self._ring, bg=THEME["surface"], padx=1, pady=1)
        ring_inner.pack()
        self.entry = tk.Entry(
            ring_inner, textvariable=self.filter_var, bd=0, relief="flat", width=16,
            bg=THEME["surface"], fg=THEME["text"], insertbackground=THEME["text"],
            font=self._font_small, highlightthickness=0,
        )
        self.entry.pack(ipady=self.px(4), ipadx=self.px(8))
        self.entry.bind("<FocusIn>", lambda e: self._ring.config(bg=THEME["primary"]))
        self.entry.bind("<FocusOut>", lambda e: self._ring.config(bg=THEME["border"]))
        # 占位提示:空态显示灰字,聚焦即清空
        self._ph_text = t("search_ph")
        self._ph_active = False
        self.entry.bind("<FocusIn>", self._ph_clear, add="+")
        self.entry.bind("<FocusOut>", self._ph_restore, add="+")
        self._ph_restore(None)
        self._search_label = tk.Label(header, text=t("search"), bg=THEME["bg"],
                                      fg=THEME["muted"], font=self._font_small)
        self._search_label.pack(side="right", padx=(0, self.px(8)))
        self._i18n_widgets.append((self._search_label, "search"))

        self.status = tk.Label(header, text="", bg=THEME["bg"], fg=THEME["muted"],
                               font=self._font_small)
        self.status.pack(side="right", padx=(0, self.px(16)))

        # ---- 列表:Canvas 自绘 ----
        body = tk.Frame(frame, bg=THEME["surface"], highlightthickness=0)
        self.canvas = tk.Canvas(body, bg=THEME["surface"], bd=0,
                                highlightthickness=0, takefocus=True)
        self.canvas.pack(fill="both", expand=True)

        # ---- 分隔条:拖动调整详情区高度 ----
        self.splitter = tk.Frame(frame, bg=THEME["bg"], height=self.px(8),
                                 cursor="sb_v_double_arrow")
        self.splitter.bind("<ButtonPress-1>", self._split_start)
        self.splitter.bind("<B1-Motion>", self._split_drag)
        self.splitter.bind("<ButtonRelease-1>", self._split_end)
        # 可见把手:居中短横条,提示可拖;悬停加深
        self._split_grip = tk.Frame(self.splitter, bg=THEME["scrollbar"],
                                    height=self.px(3), width=self.px(56))
        self._split_grip.pack(expand=True)
        self._split_grip.bind("<ButtonPress-1>", self._split_start)
        self._split_grip.bind("<B1-Motion>", self._split_drag)
        self._split_grip.bind("<ButtonRelease-1>", self._split_end)

        def _split_hover(on):
            self.splitter.config(bg=THEME["hover"] if on else THEME["bg"])
            self._split_grip.config(bg=THEME["muted"] if on else THEME["scrollbar"])

        for _w in (self.splitter, self._split_grip):
            _w.bind("<Enter>", lambda e: _split_hover(True))
            _w.bind("<Leave>", lambda e: _split_hover(False))

        # ---- 详情区(内凹明度分层替代边框) ----
        self.detail = tk.Frame(frame, bg=THEME["inset"], height=self.detail_h,
                               highlightthickness=0)
        self.detail.pack_propagate(False)
        self.detail_text = tk.Text(
            self.detail, wrap="word", bd=0, relief="flat", state="disabled", cursor="arrow",
            bg=THEME["inset"], fg=THEME["text"], font=self._fonts["detail"],
            padx=self.px(16), pady=self.px(8), highlightthickness=0,
        )
        self.detail_text.pack(fill="both", expand=True)
        self.detail_text.bind(
            "<MouseWheel>", lambda e: self.detail_text.yview_scroll(int(-e.delta / 120), "units")
        )
        self.detail_img = tk.Label(self.detail, bg=THEME["inset"], fg=THEME["muted"],
                                   font=self._font_small)
        self._show_detail_placeholder()

        # ---- 底栏:次要操作在左,主操作在右 ----
        footer = tk.Frame(frame, bg=THEME["bg"])
        self.btn_clear = self._button(footer, "btn_clear", self.clear_clicked, "danger")
        self.btn_settings = self._button(footer, "btn_settings", self.open_settings, "secondary")
        self.btn_paste = self._button(footer, "btn_paste", self.paste_selected, "primary")

        # ---- 装配:顶栏/底栏/详情先占位,列表吃剩余空间;窗口缩小时固定区永不被挤掉
        # 注意 bottom 的打包顺序:先打包者最靠下。footer → detail → splitter,
        # 分隔条才落在详情区"上边界"(用户就是拖这条)。
        footer.pack(side="bottom", fill="x", padx=pad, pady=self.px(16))
        self.detail.pack(side="bottom", fill="x", padx=pad)
        self.splitter.pack(side="bottom", fill="x", padx=pad)
        body.pack(side="top", fill="both", expand=True, padx=pad)
        self.btn_clear.pack(side="left")
        self.btn_settings.pack(side="left", padx=self.px(8))
        self.btn_paste.pack(side="right", padx=(0, self.px(20)))

        # ---- 右下角缩放热区(无边框窗口自绘) ----
        self._grip = tk.Canvas(frame, width=self.px(16), height=self.px(16),
                               bg=THEME["bg"], highlightthickness=0, cursor="size_nw_se")
        self._grip.place(relx=1.0, rely=1.0, anchor="se")
        for i, d in enumerate((4, 8, 12)):
            self._grip.create_line(self.px(d), self.px(16), self.px(16), self.px(d),
                                   fill=THEME["muted"], width=1)
        self._grip.bind("<ButtonPress-1>", self._resize_start)
        self._grip.bind("<B1-Motion>", self._resize_drag)
        self._grip.bind("<ButtonRelease-1>", self._resize_end)

        # ---- 交互绑定 ----
        self.bind("<Escape>", lambda e: self.hide())
        self.bind("<Return>", self._on_key(self.paste_selected))
        self.entry.bind("<KeyRelease>", lambda e: self.refresh())
        self.entry.bind("<Down>", self._on_key(lambda: self.move(1)))
        self.entry.bind("<Up>", self._on_key(lambda: self.move(-1)))
        self.entry.bind("<Return>", self._on_key(self.paste_selected))
        self.entry.bind("<Escape>", self._on_key(self.hide))
        # Canvas 自带方向键滚动绑定,必须在本层拦截并 return "break",否则事件到不了窗口
        self.canvas.bind("<Up>", self._on_key(lambda: self.move(-1)))
        self.canvas.bind("<Down>", self._on_key(lambda: self.move(1)))
        self.canvas.bind("<Return>", self._on_key(self.paste_selected))
        self.canvas.bind("<Escape>", self._on_key(self.hide))
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Double-Button-1>", lambda e: self.paste_selected())
        self.canvas.bind("<Motion>", self._motion)
        self.canvas.bind("<Leave>", self._leave)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Configure>", lambda e: self._redraw())
        self.canvas.bind("<FocusIn>", lambda e: self._redraw())
        self.canvas.bind("<Tab>", lambda e: (self.entry.focus_set(), "break")[1])
        self.entry.bind("<Tab>", lambda e: (self.canvas.focus_set(), "break")[1])
        self.protocol("WM_DELETE_WINDOW", self.hide)

    # ---- 搜索占位 ----
    def _ph_clear(self, _event):
        if self._ph_active:
            self._ph_active = False
            self.filter_var.set("")
            self.entry.config(fg=THEME["text"])

    def _ph_restore(self, _event):
        if not self.filter_var.get().strip():
            self._ph_active = True
            self.filter_var.set(self._ph_text)
            self.entry.config(fg=THEME["muted"])

    # ---- 尺寸与字体 ----
    def px(self, v: float) -> int:
        """逻辑像素 → 当前 DPI 下的物理像素,保持整数避免字形发虚。"""
        return max(1, int(round(v * self._s)))

    def _build_fonts(self) -> dict:
        fam = _pick_family(self)
        p = self.px
        return {
            "title": tkfont.Font(family=fam, size=-p(16), weight="bold"),
            "body": tkfont.Font(family=fam, size=-p(14)),
            "small": tkfont.Font(family=fam, size=-p(11)),
            "num": tkfont.Font(family="Consolas", size=-p(11)),  # 等宽数字,秒数不抖
            "detail": tkfont.Font(family=fam, size=-p(13)),
            "close": tkfont.Font(family="Segoe UI Symbol", size=-p(14)),
        }

    def _on_key(self, fn):
        """按键处理:执行后 return "break",阻止 Canvas/Entry 类绑定二次消费。"""
        def handler(_event=None):
            fn()
            return "break"
        return handler

    # ---- 图标按钮:右上角关闭 × ----
    def _icon_close(self, parent):
        lb = tk.Label(parent, text="✕", bg=THEME["bg"], fg=THEME["muted"],
                      font=self._fonts["close"], padx=self.px(8), pady=self.px(4),
                      cursor="hand2")

        def on_press(_e):
            lb.config(fg=THEME["danger"], bg=THEME["danger_hover"])

        def on_release(_e):
            lb.config(fg=THEME["danger"], bg=THEME["hover"])
            self.hide()

        lb.bind("<ButtonPress-1>", on_press)
        lb.bind("<ButtonRelease-1>", on_release)
        lb.bind("<Enter>", lambda e: lb.config(fg=THEME["danger"], bg=THEME["hover"]))
        lb.bind("<Leave>", lambda e: lb.config(fg=THEME["muted"], bg=THEME["bg"]))
        return lb

    # ---- 自绘按钮:主 / 次要(描边) / 危险 三套 ----
    def _button(self, parent, key, cmd, kind="secondary", text=None):
        """key 为 i18n 键;text 可覆盖(设置窗里的按钮用同一套样式)。"""
        spec = {
            "primary": dict(bg=THEME["primary"], fg="#FFFFFF",
                            hover=THEME["primary_hover"], press=THEME["primary_pressed"],
                            border=THEME["primary"]),
            "secondary": dict(bg=THEME["surface"], fg=THEME["text"],
                              hover=THEME["hover"], press=THEME["border"],
                              border=THEME["border"]),
            "danger": dict(bg=THEME["surface"], fg=THEME["danger"],
                           hover=THEME["danger_hover"], press=THEME["border"],
                           border=THEME["border"]),
        }[kind]
        lb = tk.Label(
            parent, text=text if text is not None else t(key),
            bg=spec["bg"], fg=spec["fg"], font=self._font,
            padx=self.px(16), pady=self.px(8), cursor="hand2",
            highlightbackground=spec["border"], highlightthickness=1,
        )

        def on_press(_e):
            lb.config(bg=spec["press"])

        def on_release(_e):
            # 注意:<Button-1> 与 <ButtonPress-1> 是同一事件序列,重复绑定会覆盖,
            # 因此"按下变色"和"执行命令"必须分别绑 Press / Release 两个阶段。
            lb.config(bg=spec["hover"])
            cmd()

        lb.bind("<ButtonPress-1>", on_press)
        lb.bind("<ButtonRelease-1>", on_release)
        lb.bind("<Enter>", lambda e: lb.config(bg=spec["hover"]))
        lb.bind("<Leave>", lambda e: lb.config(bg=spec["bg"]))
        self._i18n_widgets.append((lb, key))
        return lb

    def retranslate(self):
        """语言切换后重设所有静态文案,并重绘列表/详情。"""
        for widget, key in self._i18n_widgets:
            try:
                if widget.winfo_exists():
                    widget.config(text=t(key))
            except Exception:
                pass
        self._ph_text = t("search_ph")
        if self._ph_active:
            self.filter_var.set(self._ph_text)
        self.refresh()

    # ---- 显示控制 ----
    def show(self):
        """兼容入口:居中显示。"""
        self.show_at()

    def show_at(self, x: int | None = None, y: int | None = None):
        """在指定屏幕坐标显示(通常为插入光标下方),越界自动收回屏幕内。"""
        self.refresh()
        w, h = self.px(self._panel_w), self.px(self._panel_h)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        if x is None:
            x = (sw - w) // 2
        if y is None:
            y = (sh - h) // 3
        x = min(max(int(x), 0), max(0, sw - w))
        y = min(max(int(y), 0), max(0, sh - h))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.deiconify()
        self.lift()
        self.focus_force()
        # 默认焦点给列表:打开即可用方向键;搜索框留占位提示,点击或 Tab 进入
        self.canvas.focus_set()

    def hide(self):
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.destroy()
            self._settings_win = None
        self.withdraw()

    def is_visible(self) -> bool:
        return self.state() == "normal"

    # ---- 数据 ----
    def refresh(self):
        raw = self.filter_var.get().strip()
        if raw and raw != getattr(self, "_ph_text", ""):
            self._ph_active = False           # 外部直接写入关键词时退出占位态
        keyword = "" if self._ph_active else raw.lower()
        prev_id = self._items[self._sel].id if 0 <= self._sel < len(self._items) else None
        self._items = [
            it for it in self.app.storage.all_newest_first()
            if not keyword or keyword in it.preview().lower() or keyword in it.text.lower()
        ]
        self._sel = -1
        if self._items:
            self._sel = 0
            for i, it in enumerate(self._items):  # 保持原选中条目
                if it.id == prev_id:
                    self._sel = i
                    break
        self._hover = -1
        self.canvas.yview_moveto(0)
        self._redraw()
        self._render_detail()
        self._reset_status()

    def _reset_status(self):
        """状态栏回到计数(2.5s 自熄后调用)。"""
        if self._status_job:
            try:
                self.after_cancel(self._status_job)
            except Exception:
                pass
        self._status_job = None
        self.status.config(text=t("count", n=len(self._items), total=self.app.storage.count()),
                           fg=THEME["muted"])

    def _flash_status(self, msg: str, ms: int = 2500):
        """临时反馈:显示 2.5s 后自动淡出恢复计数,无需手动清理。"""
        if self._status_job:
            self.after_cancel(self._status_job)
        self.status.config(text=msg, fg=THEME["primary"])
        self._status_job = self.after(ms, self._reset_status)

    def row_count(self) -> int:
        return len(self._items)

    def select_index(self, i: int):
        if 0 <= i < len(self._items):
            self._sel = i
            self._ensure_visible(i)
            self._redraw()
            self._render_detail()

    def selected_item(self):
        if 0 <= self._sel < len(self._items):
            return self._items[self._sel]
        return None

    # ---- 绘制 ----
    def _redraw(self):
        c = self.canvas
        c.delete("all")
        w = max(c.winfo_width(), self.px(MIN_W) - self.px(48))
        h = max(c.winfo_height(), 1)
        c.config(scrollregion=(0, 0, w, max(len(self._items) * self.row_h, h)))

        if not self._items:
            c.create_text(w // 2, h // 2, text=t("empty"),
                          fill=THEME["muted"], font=self._font)
            return

        pad_l = self.px(16)      # 左侧内边距
        chip_r = self.px(10)     # 徽标半径
        text_x = pad_l + self.px(30)
        time_w = self.px(76)
        pad_r = self.px(16)

        for i, it in enumerate(self._items):
            y = i * self.row_h
            if i == self._sel:
                fill = THEME["selected"]
            elif i == self._hover:
                fill = THEME["hover"]
            else:
                fill = THEME["surface"]
            c.create_rectangle(0, y, w, y + self.row_h, fill=fill, outline="")
            if i == self._sel:  # 左侧强调条
                c.create_rectangle(0, y + self.px(8), self.px(3), y + self.row_h - self.px(8),
                                   fill=THEME["primary"], outline="")

            cy = y + self.row_h // 2
            kind = it.kind if it.kind in THEME["chip"] else "text"
            c.create_oval(pad_l, cy - chip_r, pad_l + chip_r * 2, cy + chip_r,
                          fill=THEME["chip"][kind], outline="")
            # 字形按视觉中心上移 1px(等价 CSS vertical-align:-0.125em)
            c.create_text(pad_l + chip_r, cy - 1, text=t(f"glyph_{kind}"), fill="#FFFFFF",
                          font=self._font_small)

            stamp = time.strftime("%H:%M:%S", time.localtime(it.ts))
            c.create_text(w - pad_r, cy, text=stamp, fill=THEME["muted"],
                          font=self._font_num, anchor="e")

            avail = w - text_x - time_w - pad_r
            c.create_text(text_x, cy, text=self._fit(it.preview(), avail),
                          fill=THEME["text"], font=self._font, anchor="w")

        self._sync_scrollbar()

    def _fit(self, text: str, max_w: float) -> str:
        if self._font.measure(text) <= max_w:
            return text
        lo, hi = 0, len(text)
        while lo < hi:  # 二分查找截断点,避免逐字测量
            mid = (lo + hi) // 2
            if self._font.measure(text[:mid] + "…") <= max_w:
                lo = mid + 1
            else:
                hi = mid
        return text[:max(lo - 1, 0)] + "…"

    def _sync_scrollbar(self):
        c = self.canvas
        c.delete("sbar")
        first, last = c.yview()
        if last - first >= 0.999:
            return
        top = c.canvasy(0)
        h = c.winfo_height()
        x = c.winfo_width() - self.px(8)
        c.create_rectangle(x, top + first * h, x + self.px(4), top + last * h,
                           fill=THEME["scrollbar"], outline="", tags="sbar")

    # ---- 鼠标事件 ----
    def _click(self, event):
        self.select_index(int(self.canvas.canvasy(event.y) // self.row_h))

    def _motion(self, event):
        i = int(self.canvas.canvasy(event.y) // self.row_h)
        if 0 <= i < len(self._items):
            self.canvas.config(cursor="hand2")   # 可点击区域给手型
            if i != self._hover:
                self._hover = i
                self._redraw()
        else:
            self.canvas.config(cursor="")

    def _leave(self, event):
        self.canvas.config(cursor="")
        if self._hover != -1:
            self._hover = -1
            self._redraw()

    def _wheel(self, event):
        self.canvas.yview_scroll(-1 * (event.delta // 120), "units")
        self._sync_scrollbar()

    def move(self, delta: int):
        if not self._items:
            return
        self.select_index(min(max(self._sel + delta, 0), len(self._items) - 1))

    def _ensure_visible(self, i: int):
        total = len(self._items) * self.row_h
        if total <= 0:
            return
        h = self.canvas.winfo_height()
        if h <= 1:
            return
        top = self.canvas.yview()[0] * total
        y = i * self.row_h
        if y < top:
            self.canvas.yview_moveto(y / total)
        elif y + self.row_h > top + h:
            self.canvas.yview_moveto(max(0.0, (y + self.row_h - h) / total))

    # ---- 面板拖动(无边框窗口,自绘标题栏拖拽) ----
    def _drag_start(self, event):
        self._drag_origin = (event.x_root, event.y_root, self.winfo_x(), self.winfo_y())

    def _drag_move(self, event):
        if not self._drag_origin:
            return
        x0, y0, wx, wy = self._drag_origin
        self.geometry(f"+{wx + event.x_root - x0}+{wy + event.y_root - y0}")

    # ---- 面板缩放手柄 ----
    def _resize_start(self, event):
        self._resize_origin = (event.x_root, event.y_root,
                               self.winfo_width(), self.winfo_height())

    def _resize_drag(self, event):
        if not self._resize_origin:
            return
        x0, y0, w0, h0 = self._resize_origin
        w = max(self.px(MIN_W), w0 + (event.x_root - x0))
        h = max(self.px(MIN_H), h0 + (event.y_root - y0))
        self.geometry(f"{w}x{h}")

    def _resize_end(self, event):
        if not self._resize_origin:
            return
        self._resize_origin = None
        self._panel_w = max(MIN_W, int(round(self.winfo_width() / self._s)))
        self._panel_h = max(MIN_H, int(round(self.winfo_height() / self._s)))
        st = config.load_settings()
        st["panel_w"], st["panel_h"] = self._panel_w, self._panel_h
        config.save_settings(st)
        self._apply_detail_height(self.selected_item())
        self._redraw()

    # ---- 详情区高度:拖动分隔条固定,否则跟随内容 ----
    def _split_start(self, event):
        self._split_origin = (event.y_root, self.detail.winfo_height())

    def _split_drag(self, event):
        if not self._split_origin:
            return
        y0, h0 = self._split_origin
        h = max(self.px(56), min(self.px(400), h0 - (event.y_root - y0)))
        self.detail.config(height=h)
        self._detail_fixed_h = max(56, int(round(h / self._s)))

    def _split_end(self, event):
        if not self._split_origin:
            return
        self._split_origin = None
        st = config.load_settings()
        st["detail_h"] = self._detail_fixed_h
        config.save_settings(st)
        self._render_detail()   # 图片缩略图按新高度重算

    def _apply_detail_height(self, item):
        if self._detail_fixed_h:
            h = self.px(self._detail_fixed_h)
        elif item is not None and item.kind == "image":
            h = self.detail_h
        else:
            if item is None:
                lines = 1
            elif item.kind == "files":
                lines = max(1, len(item.files))
            else:
                per_line = max(16, int(self.px(520) / max(1, self._fonts["detail"].measure("中"))))
                lines = sum(max(1, -(-len(seg) // per_line)) for seg in item.text.split("\n"))
            h = self.px(16) + max(1, lines) * self.px(20)
            h = max(self.px(56), min(self.detail_h, h))
        if int(self.detail.cget("height")) != h:
            self.detail.config(height=h)

    # ---- 详情区内容 ----
    def _show_detail_placeholder(self):
        self._apply_detail_height(None)
        self.detail_img.pack_forget()
        if not self.detail_text.winfo_ismapped():
            self.detail_text.pack(fill="both", expand=True)
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", t("detail_ph"))
        self.detail_text.tag_add("muted", "1.0", "end")
        self.detail_text.tag_config("muted", foreground=THEME["muted"])
        self.detail_text.config(state="disabled")

    def _render_detail(self):
        item = self.selected_item()
        self._apply_detail_height(item)
        if item is None:
            self._show_detail_placeholder()
            return
        if item.kind == "image":
            self.detail_text.pack_forget()
            self.detail_img.pack(fill="both", expand=True)
            path = os.path.join(config.IMAGE_DIR, item.image_file)
            try:
                img = Image.open(path)
                avail_h = max(self.px(80), self.detail.winfo_height() - self.px(24))
                img.thumbnail((self.px(520), avail_h))
                self._thumb_ref = ImageTk.PhotoImage(img)
                self.detail_img.config(image=self._thumb_ref, text="")
            except Exception:
                self.detail_img.config(image="", text=t("image_missing"))
            return
        self.detail_img.pack_forget()
        if not self.detail_text.winfo_ismapped():
            self.detail_text.pack(fill="both", expand=True)
        if item.kind == "text":
            content = item.text
        else:
            content = "\n".join(
                p if os.path.exists(p) else t("file_missing", path=p) for p in item.files
            )
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", content)
        self.detail_text.config(state="disabled")
        self.detail_text.yview_moveto(0)

    # ---- 设置面板 ----
    def open_settings(self):
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.lift()
            self._settings_win.focus_force()
            return

        win = tk.Toplevel(self)
        self._settings_win = win
        win.title(t("settings_title"))
        win.configure(bg=THEME["bg"])
        win.resizable(False, False)
        win.transient(self)
        # 父面板是置顶无边框窗口,设置窗必须同样置顶,否则会被盖住(lift 也不一定够)
        win.attributes("-topmost", True)
        pad = self.px(24)

        # 语言
        tk.Label(win, text=t("sec_language"), bg=THEME["bg"], fg=THEME["text"],
                 font=self._font_title).grid(row=0, column=0, sticky="w",
                                            padx=pad, pady=(pad, self.px(4)))
        self._lang_var = tk.StringVar(value=i18n.get_lang())
        lang_row = tk.Frame(win, bg=THEME["bg"])
        lang_row.grid(row=1, column=0, sticky="w", padx=pad, pady=(0, self.px(16)))
        for code, label in i18n.LANGS.items():
            tk.Radiobutton(
                lang_row, text=label, variable=self._lang_var, value=code,
                command=self._apply_language, bg=THEME["bg"], fg=THEME["text"],
                selectcolor=THEME["surface"], activebackground=THEME["bg"],
                activeforeground=THEME["text"], font=self._font, bd=0,
                highlightthickness=0, cursor="hand2",
            ).pack(side="left", padx=(0, self.px(20)))

        # 粘贴后行为:单项开关(勾选=保持打开连续粘贴)
        tk.Label(win, text=t("sec_paste"), bg=THEME["bg"], fg=THEME["text"],
                 font=self._font_title).grid(row=2, column=0, sticky="w",
                                            padx=pad, pady=(0, self.px(4)))
        self._keep_open_var = tk.BooleanVar(value=not self.hide_after_paste)
        tk.Checkbutton(
            win, text=t("keep_open"), variable=self._keep_open_var,
            command=self._apply_paste_mode, bg=THEME["bg"], fg=THEME["text"],
            selectcolor=THEME["surface"], activebackground=THEME["bg"],
            activeforeground=THEME["text"], font=self._font, bd=0,
            highlightthickness=0, anchor="w", cursor="hand2",
        ).grid(row=3, column=0, sticky="w", padx=pad, pady=self.px(4))

        tk.Label(win, text=t("hint"), bg=THEME["bg"], fg=THEME["muted"],
                 font=self._font_small).grid(row=4, column=0, sticky="w",
                                            padx=pad, pady=(self.px(16), 0))

        row = tk.Frame(win, bg=THEME["bg"])
        row.grid(row=5, column=0, sticky="ew", padx=pad, pady=self.px(16))
        self._button(row, "reset_sizes", self._reset_sizes, "secondary").pack(side="left")
        self._button(row, "btn_close", win.destroy, "primary").pack(side="right")

        # 居中于面板上方
        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - h) // 2
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
        win.lift()
        win.focus_force()

    def _apply_paste_mode(self):
        self.hide_after_paste = not bool(self._keep_open_var.get())
        st = config.load_settings()
        st["hide_after_paste"] = self.hide_after_paste
        config.save_settings(st)
        self._flash_status(t("status_saved"))

    def _apply_language(self):
        lang = self._lang_var.get()
        if lang == i18n.get_lang():
            return
        i18n.set_lang(lang)
        st = config.load_settings()
        st["language"] = lang
        config.save_settings(st)
        self.app.on_language_changed()
        # 设置窗自身文案也要换:重建一次并保持原位置
        if self._settings_win and self._settings_win.winfo_exists():
            pos = (self._settings_win.winfo_x(), self._settings_win.winfo_y())
            self._settings_win.destroy()
            self._settings_win = None
            self.open_settings()
            self._settings_win.geometry(f"+{pos[0]}+{pos[1]}")
        self._flash_status(t("status_saved"))

    def _reset_sizes(self):
        self._panel_w, self._panel_h = DEFAULT_W, DEFAULT_H
        self._detail_fixed_h = 0
        st = config.load_settings()
        st.update(panel_w=DEFAULT_W, panel_h=DEFAULT_H, detail_h=0)
        config.save_settings(st)
        self.geometry(f"{self.px(self._panel_w)}x{self.px(self._panel_h)}")
        self._apply_detail_height(self.selected_item())
        self._flash_status(t("status_sizes_reset"))

    # ---- 动作 ----
    def paste_selected(self):
        item = self.selected_item()
        if item is None:
            self._flash_status(t("status_nothing"))
            return
        if item.kind == "files":
            missing = [p for p in item.files if not os.path.exists(p)]
            if missing:
                self._flash_status(t("status_missing_files", n=len(missing)))
        self.app.paste_item(item)

    def clear_clicked(self):
        # 原生确认框会被置顶面板盖住,临时取消置顶再弹
        self.attributes("-topmost", False)
        try:
            ok = messagebox.askyesno(t("confirm_title"), t("confirm_body"), parent=self)
        finally:
            self.attributes("-topmost", True)
        if ok:
            self.app.clear_all(confirm=False)
            self.refresh()
            self._flash_status(t("status_cleared"))
