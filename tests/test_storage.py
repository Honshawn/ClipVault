"""存储层测试:FIFO 淘汰 / 相邻去重 / 一键清空 / 持久化恢复 / 损坏自愈。
运行: python tests/test_storage.py
"""
import os
import sys
import tempfile

# CI(cp1252 控制台)与本地(cp936)都能正常输出中文
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

_tmp = tempfile.mkdtemp(prefix="clipvault_test_")
config.DATA_DIR = _tmp
config.HISTORY_FILE = os.path.join(_tmp, "history.json")
config.IMAGE_DIR = os.path.join(_tmp, "images")

from storage import ClipItem, HistoryStorage

passed = 0


def check(name, cond):
    global passed
    assert cond, f"FAIL: {name}"
    passed += 1
    print(f"  PASS {name}")


def make_text_item(i):
    return ClipItem(kind="text", text=f"text-{i}", content_hash=f"h{i}")


# 1. FIFO:灌入 101 条,剩 100 条且最旧的 text-0 被淘汰
s = HistoryStorage()
for i in range(101):
    s.add(make_text_item(i))
items = s.all_newest_first()
check("FIFO: 101 入队后剩 100 条", s.count() == 100)
check("FIFO: 最旧的 text-0 已被淘汰", items[-1].text == "text-1")
check("FIFO: 最新的 text-100 排在最前", items[0].text == "text-100")
s.flush()   # 写盘是防抖的,测试需要确定性

# 2. 相邻去重
s2 = HistoryStorage()
s2.add(ClipItem(kind="text", text="abc", content_hash="h1"))
added = s2.add(ClipItem(kind="text", text="abc", content_hash="h1"))
check("去重: 相同内容连续复制不入队", added is False and s2.count() == 1)
s2.add(ClipItem(kind="text", text="def", content_hash="h2"))
s2.add(ClipItem(kind="text", text="abc", content_hash="h1"))
check("去重: 非相邻的相同内容正常入队", s2.count() == 3)
s2.flush()

# 3. 一键清空(含图片文件)
s3 = HistoryStorage()
fname = s3.save_image(b"\x89PNG fake-bytes")
s3.add(ClipItem(kind="image", image_file=fname, content_hash="img1"))
s3.add(make_text_item(1))
s3.clear()
check("清空: 队列为 0", s3.count() == 0)
check("清空: 图片文件已删除", os.listdir(config.IMAGE_DIR) == [])
check("清空: 最新条目为 None", s3.latest() is None)

# 4. 持久化恢复
s4 = HistoryStorage()
s4.add(make_text_item(1))
s4.add(make_text_item(2))
fname2 = s4.save_image(b"\x89PNG img2")
s4.add(ClipItem(kind="image", image_file=fname2, content_hash="img2"))
s4.add(ClipItem(kind="files", files=["C:/a.txt", "D:/b.docx"], content_hash="f1"))
s4.flush()   # 防抖写盘:落盘后再模拟重启
s5 = HistoryStorage()
s5.load()
loaded = s5.all_newest_first()
check("持久化: 重启后条数一致", s5.count() == 4)
check("持久化: 顺序一致(最新在前)", [it.id for it in loaded] == [it.id for it in s4.all_newest_first()])
check("持久化: files 字段完整", loaded[0].files == ["C:/a.txt", "D:/b.docx"])

# 5. 引用丢失图片的条目在加载时被跳过
os.remove(os.path.join(config.IMAGE_DIR, fname2))
s6 = HistoryStorage()
s6.load()
check("持久化: 图片文件丢失的条目被跳过", s6.count() == 3)

# 6. 损坏的 history.json → 改名 .bad 且空历史启动
s6.flush()   # 先落盘,避免防抖定时器覆盖下面写入的损坏文件
with open(config.HISTORY_FILE, "w", encoding="utf-8") as f:
    f.write("{not-valid-json")
s7 = HistoryStorage()
s7.load()
check("自愈: 损坏文件改名 .bad", os.path.exists(config.HISTORY_FILE + ".bad"))
check("自愈: 损坏后以空历史启动", s7.count() == 0)

# 7. 并发落盘不产生损坏文件(定时器线程与 flush 同时写)
import threading
if os.path.exists(config.HISTORY_FILE + ".bad"):
    os.remove(config.HISTORY_FILE + ".bad")   # 清掉上一条用例故意留下的损坏文件
s8 = HistoryStorage()
s8.add(make_text_item(8))
threads = [threading.Thread(target=s8.flush) for _ in range(8)]
for th in threads:
    th.start()
for th in threads:
    th.join()
s9 = HistoryStorage()
s9.load()
check("并发: 多线程 flush 后文件仍可解析", s9.count() == 1)
check("并发: .bad 未被触发", not os.path.exists(config.HISTORY_FILE + ".bad"))

print(f"\n全部通过: {passed} 项")
