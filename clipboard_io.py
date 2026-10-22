"""剪贴板底层读写(Win32):文本 / 图片(CF_DIB) / 文件列表(CF_HDROP)。"""
from __future__ import annotations

import hashlib
import io
import struct
import time

import win32clipboard
import win32con
from PIL import Image

CF_DIBV5 = 17


def md5(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.md5(data).hexdigest()


def get_sequence() -> int:
    return win32clipboard.GetClipboardSequenceNumber()


def _open(retry: int = 5, delay: float = 0.05) -> bool:
    """剪贴板常被其他程序短暂占用,失败重试(放行+跳过档由调用方决定)。"""
    for _ in range(retry):
        try:
            win32clipboard.OpenClipboard()
            return True
        except Exception:
            time.sleep(delay)
    return False


# ---- 读取 ----

def read_clipboard() -> dict | None:
    """读当前剪贴板,返回 {kind, ...} 或 None(无可识别格式)。优先级:文件 > 图片 > 文本。"""
    if not _open():
        return None
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_HDROP):
            files = list(win32clipboard.GetClipboardData(win32con.CF_HDROP))
            if files:
                return {"kind": "files", "files": files}
        for fmt in (win32con.CF_DIB, CF_DIBV5):
            if win32clipboard.IsClipboardFormatAvailable(fmt):
                dib = win32clipboard.GetClipboardData(fmt)
                if dib:
                    png = dib_to_png(dib)
                    if png:
                        return {"kind": "image", "png": png, "hash": md5(dib)}
                break  # 有 DIB 但解析失败不再降级当文本
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            if text:
                return {"kind": "text", "text": text}
        return None
    finally:
        win32clipboard.CloseClipboard()


def dib_to_png(dib: bytes) -> bytes | None:
    """CF_DIB 缺 BMP 14 字节文件头,手工补齐后用 Pillow 解析转 PNG。"""
    try:
        header_size = struct.unpack_from("<I", dib, 0)[0]
        bpp = struct.unpack_from("<H", dib, 14)[0]
        clr_used = struct.unpack_from("<I", dib, 32)[0] if len(dib) >= 36 else 0
        colors = clr_used if clr_used else ((1 << bpp) if bpp <= 8 else 0)
        pixel_offset = 14 + header_size + colors * 4
        bmp = b"BM" + struct.pack("<IHHI", 14 + len(dib), 0, 0, pixel_offset) + dib
        img = Image.open(io.BytesIO(bmp))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()
    except Exception:
        return None  # 私有/异常格式:跳过不入队


# ---- 写入 ----

def _write(fmt, data) -> bool:
    if not _open():
        return False
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(fmt, data)
        return True
    except Exception:
        return False
    finally:
        win32clipboard.CloseClipboard()


def write_text(text: str) -> bool:
    return _write(win32con.CF_UNICODETEXT, text)


def write_image(png_path: str) -> bool:
    img = Image.open(png_path)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "BMP")
    dib = buf.getvalue()[14:]  # 剥掉 14 字节文件头即 DIB
    return _write(win32con.CF_DIB, dib)


def write_files(paths: list) -> bool:
    # pywin32 的 CF_HDROP 只接受 bytes,手工拼 DROPFILES 结构:
    # DWORD pFiles(=20) + POINT pt + BOOL fNC + BOOL fWide(=1) + 双 \0 结尾的 UTF-16 路径列表
    files = ("\0".join(paths) + "\0\0").encode("utf-16-le")
    dropfiles = struct.pack("<IiiII", 20, 0, 0, 0, 1) + files
    return _write(win32con.CF_HDROP, dropfiles)


def write_item(kind: str, *, text: str = "", image_path: str = "", files: list | None = None) -> bool:
    if kind == "text":
        return write_text(text)
    if kind == "image":
        return write_image(image_path)
    if kind == "files":
        return write_files(files or [])
    return False
