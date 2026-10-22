"""集中配置:改热键、容量、目录都来这里。用户可调项另存 settings.json。"""
import json
import os

APP_NAME = "ClipVault"

# 历史容量与体积上限
MAX_ITEMS = 100                     # 历史最大条数,超出按 FIFO 淘汰最旧
MAX_TEXT_BYTES = 1 * 1024 * 1024    # 单条文本最大 1MB,超出截断
MAX_IMAGE_BYTES = 50 * 1024 * 1024  # 单张图片最大 50MB,超出拒绝入队

# 交互
POLL_INTERVAL = 0.3                 # 剪贴板轮询间隔(秒)
DOUBLE_CTRL_WINDOW = 0.35           # 双击 Ctrl 判定窗口(秒)
HOTKEY_PASTE_LATEST = "ctrl+alt+v"  # 直接粘贴最新一条

# 数据目录(图片、历史、用户设置持久化位置)
DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
IMAGE_DIR = os.path.join(DATA_DIR, "images")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

# 用户可调项(面板内"设置"按钮修改,存盘后下次启动生效)
DEFAULT_SETTINGS = {
    "hide_after_paste": True,   # 粘贴后隐藏面板;False = 保持打开连续粘贴
    "language": "zh",           # 界面语言:zh / en
    "panel_w": 620,             # 面板逻辑宽度(96 DPI)
    "panel_h": 660,             # 面板逻辑高度
    "detail_h": 0,              # 详情区固定高度;0 = 跟随内容自适应
}


def load_settings() -> dict:
    """读用户设置;缺项用默认值补齐,文件损坏按默认值启动。"""
    data = {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            data = raw
    except (OSError, json.JSONDecodeError):
        data = {}
    merged = dict(DEFAULT_SETTINGS)
    merged.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
    return merged


def save_settings(data: dict):
    """原子写入设置(临时文件 + 替换),失败不影响运行。"""
    merged = dict(DEFAULT_SETTINGS)
    merged.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = SETTINGS_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_FILE)
    except OSError:
        pass
