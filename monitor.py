"""剪贴板监听:轮询序列号,变化时抓取内容回调;程序自身写入可被标记忽略。"""
from __future__ import annotations

import threading
import time

import clipboard_io
import config


class ClipboardMonitor(threading.Thread):
    def __init__(self, on_new):
        """
        on_new(data: dict): 新复制内容回调,data 为 clipboard_io.read_clipboard() 的返回。
        """
        super().__init__(daemon=True, name="ClipboardMonitor")
        self.on_new = on_new
        self._last_seq = 0
        self._own_write = False
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self.errors: list[str] = []

    def note_own_write(self):
        """程序自己写剪贴板前调用,下一次变化不触发回调(防自复制循环)。"""
        with self._lock:
            self._own_write = True

    def cancel_own_write(self):
        with self._lock:
            self._own_write = False

    def stop(self):
        self._stop_event.set()

    def run(self):
        try:
            self._last_seq = clipboard_io.get_sequence()
        except Exception:
            pass
        while not self._stop_event.is_set():
            try:
                seq = clipboard_io.get_sequence()
            except Exception:
                time.sleep(config.POLL_INTERVAL)
                continue
            if seq != self._last_seq:
                self._last_seq = seq
                with self._lock:
                    own = self._own_write
                    if own:
                        self._own_write = False
                if not own:
                    try:
                        data = clipboard_io.read_clipboard()
                        if data:
                            self.on_new(data)
                    except Exception as e:
                        self.errors.append(f"{time.strftime('%H:%M:%S')} {e}")
                        del self.errors[:-50]   # 只留最近 50 条,防长期运行内存增长
            time.sleep(config.POLL_INTERVAL)
