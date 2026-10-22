"""历史存储:100 条 FIFO 队列 + 本地持久化。

FIFO 语义:deque(maxlen=100) 左侧(最旧)自动被淘汰,满足
"超过 100 个时每复制一个删去最先存储的一个"。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field

import config


@dataclass
class ClipItem:
    kind: str                                # 'text' | 'image' | 'files'
    text: str = ""                           # kind=text 时的全文
    image_file: str = ""                     # kind=image 时 IMAGE_DIR 下的 PNG 文件名
    files: list = field(default_factory=list)  # kind=files 时的绝对路径列表
    content_hash: str = ""                   # 相邻去重用
    ts: float = 0.0
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def preview(self) -> str:
        if self.kind == "text":
            s = " ".join(self.text.split())
            return s[:80] + ("..." if len(s) > 80 else "")
        if self.kind == "image":
            return self.text or "image"   # 存尺寸(如 640×360),没有则退化为类型名
        names = [os.path.basename(p) for p in self.files]
        if len(names) <= 2:
            return ", ".join(names)
        return f"{names[0]}, {names[1]} 等 {len(names)} 个"

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "text": self.text, "image_file": self.image_file,
            "files": self.files, "content_hash": self.content_hash,
            "ts": self.ts, "id": self.id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ClipItem":
        return cls(
            kind=d.get("kind", "text"), text=d.get("text", ""),
            image_file=d.get("image_file", ""), files=list(d.get("files", [])),
            content_hash=d.get("content_hash", ""), ts=d.get("ts", 0.0),
            id=d.get("id") or uuid.uuid4().hex[:8],
        )


class HistoryStorage:
    """线程安全的历史容器。监听器在锁外回调,签名 fn()。"""

    def __init__(self):
        self._items: deque[ClipItem] = deque(maxlen=config.MAX_ITEMS)
        self._lock = threading.Lock()
        self._listeners = []
        self._save_lock = threading.Lock()
        self._save_timer = None
        self._dirty = False
        os.makedirs(config.IMAGE_DIR, exist_ok=True)

    # ---- 监听器 ----
    def add_listener(self, fn):
        self._listeners.append(fn)

    def _notify(self):
        for fn in list(self._listeners):
            try:
                fn()
            except Exception:
                pass  # UI 回调异常不拖垮存储

    # ---- 写 ----
    def add(self, item: ClipItem) -> bool:
        """入队;与最新一条内容相同则跳过。返回是否真正入队。"""
        with self._lock:
            if self._items and item.content_hash and \
                    self._items[-1].content_hash == item.content_hash:
                return False
            item.ts = item.ts or time.time()
            self._items.append(item)  # 超 maxlen 自动弹出最旧
        self._notify()
        self._request_save()   # 防抖写盘,避免大历史阻塞监听线程
        return True

    def clear(self):
        """一键清空:队列 + 持久化文件 + 图片目录。清空立即落盘,不等防抖。"""
        with self._lock:
            self._items.clear()
            for name in os.listdir(config.IMAGE_DIR):
                try:
                    os.remove(os.path.join(config.IMAGE_DIR, name))
                except OSError:
                    pass
        self.flush()
        self._notify()

    def save_image(self, png_bytes: bytes) -> str:
        """落盘 PNG,返回文件名。超限抛 ValueError(拒绝档)。"""
        if len(png_bytes) > config.MAX_IMAGE_BYTES:
            raise ValueError(f"图片超过 {config.MAX_IMAGE_BYTES // 1024 // 1024}MB,拒绝入队")
        name = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}.png"
        with open(os.path.join(config.IMAGE_DIR, name), "wb") as f:
            f.write(png_bytes)
        return name

    # ---- 读 ----
    def latest(self) -> ClipItem | None:
        with self._lock:
            return self._items[-1] if self._items else None

    def all_newest_first(self) -> list:
        with self._lock:
            return list(reversed(self._items))

    def count(self) -> int:
        with self._lock:
            return len(self._items)

    # ---- 持久化 ----
    def _snapshot(self) -> list:
        with self._lock:
            return [it.to_dict() for it in self._items]

    def _request_save(self):
        """防抖:0.6s 内的连续复制只写一次盘,写入放到后台线程。"""
        with self._save_lock:
            self._dirty = True
            if self._save_timer and self._save_timer.is_alive():
                return
            self._save_timer = threading.Timer(0.6, self._flush)
            self._save_timer.daemon = True
            self._save_timer.start()

    def _flush(self):
        with self._save_lock:
            if not self._dirty:
                return
            self._dirty = False
        self._write(self._snapshot())

    def flush(self):
        """立即落盘(退出/清空/测试用)。"""
        with self._save_lock:
            if self._save_timer and self._save_timer.is_alive():
                self._save_timer.cancel()
            self._save_timer = None
            self._dirty = False
        self._write(self._snapshot())

    @staticmethod
    def _write(data: list):
        tmp = config.HISTORY_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, config.HISTORY_FILE)
        except OSError:
            pass  # 持久化失败不影响内存运行

    def load(self):
        """启动时恢复;文件损坏则改名 .bad 后以空历史启动(放行+标记)。"""
        if not os.path.exists(config.HISTORY_FILE):
            return
        try:
            with open(config.HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = []
            for d in data[-config.MAX_ITEMS:]:
                it = ClipItem.from_dict(d)
                if it.kind == "image":
                    path = os.path.join(config.IMAGE_DIR, it.image_file)
                    if not it.image_file or not os.path.exists(path):
                        continue  # 图片文件丢失的条目跳过
                items.append(it)
            with self._lock:
                self._items = deque(items, maxlen=config.MAX_ITEMS)
        except (json.JSONDecodeError, OSError, TypeError):
            try:
                os.replace(config.HISTORY_FILE, config.HISTORY_FILE + ".bad")
            except OSError:
                pass
