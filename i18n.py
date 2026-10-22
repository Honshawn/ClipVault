"""多语言文案:中文 / English。

用法:t("btn_paste");带参数 t("count", n=3, total=100)。
语言存 settings.json,启动时由 main 读取并 set_lang()。
"""
from __future__ import annotations

LANGS = {"zh": "中文", "en": "English"}

_STRINGS = {
    "zh": {
        # 面板
        "title": "剪贴板历史",
        "search": "搜索",
        "search_ph": "输入关键词过滤",
        "btn_paste": "粘贴",
        "btn_clear": "清空历史",
        "btn_close": "关闭",
        "btn_settings": "设置",
        "empty": "还没有复制记录",
        "detail_ph": "选中条目后在此查看完整内容",
        "image_missing": "图片文件已丢失",
        "file_missing": "{path}  (不存在)",
        "count": "{n}/{total} 条",
        "status_saved": "已保存",
        "status_cleared": "已清空",
        "status_nothing": "没有可粘贴的条目",
        "status_missing_files": "{n} 个源文件已不存在",
        "status_sizes_reset": "尺寸已恢复默认",
        "confirm_title": "清空历史",
        "confirm_body": "确定要清空全部复制历史吗?此操作不可恢复。",
        # 设置窗口
        "settings_title": "设置",
        "sec_language": "语言 / Language",
        "sec_paste": "粘贴后行为",
        "keep_open": "粘贴后保持面板打开,可连续粘贴",
        "hint": "面板右下角可拖动缩放;列表与详情之间的横条可调详情区高度",
        "reset_sizes": "恢复默认尺寸",
        # 托盘
        "tray_show": "显示/隐藏面板 (双击Ctrl)",
        "tray_paste": "粘贴最新 ({hotkey})",
        "tray_clear": "清空历史",
        "tray_quit": "退出",
        "tray_tip": "ClipVault 剪贴板历史",
        "glyph_text": "文",
        "glyph_image": "图",
        "glyph_files": "件",
    },
    "en": {
        "title": "Clipboard History",
        "search": "Search",
        "search_ph": "Filter by keyword",
        "btn_paste": "Paste",
        "btn_clear": "Clear All",
        "btn_close": "Close",
        "btn_settings": "Settings",
        "empty": "No clipboard history yet",
        "detail_ph": "Select an item to preview its content",
        "image_missing": "Image file is missing",
        "file_missing": "{path}  (not found)",
        "count": "{n}/{total} items",
        "status_saved": "Saved",
        "status_cleared": "Cleared",
        "status_nothing": "Nothing to paste",
        "status_missing_files": "{n} source file(s) no longer exist",
        "status_sizes_reset": "Size restored to default",
        "confirm_title": "Clear History",
        "confirm_body": "Clear all clipboard history? This cannot be undone.",
        "settings_title": "Settings",
        "sec_language": "Language / 语言",
        "sec_paste": "After pasting",
        "keep_open": "Keep panel open after pasting for consecutive pastes",
        "hint": "Drag the bottom-right corner to resize; drag the bar above the preview to resize it",
        "reset_sizes": "Reset size",
        "tray_show": "Show/Hide Panel (double Ctrl)",
        "tray_paste": "Paste Latest ({hotkey})",
        "tray_clear": "Clear History",
        "tray_quit": "Quit",
        "tray_tip": "ClipVault clipboard history",
        "glyph_text": "T",
        "glyph_image": "I",
        "glyph_files": "F",
    },
}

_lang = "zh"


def set_lang(lang: str):
    global _lang
    _lang = lang if lang in _STRINGS else "zh"


def get_lang() -> str:
    return _lang


def t(key: str, **kw) -> str:
    table = _STRINGS.get(_lang) or _STRINGS["zh"]
    text = table.get(key) or _STRINGS["zh"].get(key, key)
    return text.format(**kw) if kw else text
