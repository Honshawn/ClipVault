"""剪贴板真实读写回环测试(会临时占用本机剪贴板)。
运行: python tests/test_clipboard_roundtrip.py
"""
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

import clipboard_io

passed = 0


def check(name, cond):
    global passed
    assert cond, f"FAIL: {name}"
    passed += 1
    print(f"  PASS {name}")


# 1. 文本 roundtrip
assert clipboard_io.write_text("ClipVault 中文测试 hello")
data = clipboard_io.read_clipboard()
check("文本: 写入后能读回", data and data["kind"] == "text")
check("文本: 内容一致(含中文)", data["text"] == "ClipVault 中文测试 hello")

# 2. 图片 roundtrip:生成测试图 → write_image → 读回应为 image
img = Image.new("RGB", (64, 48), (200, 30, 30))
tmp_png = os.path.join(tempfile.mkdtemp(), "t.png")
img.save(tmp_png)
assert clipboard_io.write_image(tmp_png)
data = clipboard_io.read_clipboard()
check("图片: 写入后能读回为 image", data and data["kind"] == "image")
rt = Image.open(io.BytesIO(data["png"]))
check("图片: 回读尺寸正确", rt.size == (64, 48))

# 3. 文件列表 roundtrip
d = tempfile.mkdtemp()
f1 = os.path.join(d, "a.txt"); open(f1, "w").write("1")
f2 = os.path.join(d, "b.txt"); open(f2, "w").write("2")
assert clipboard_io.write_files([f1, f2])
data = clipboard_io.read_clipboard()
check("文件: 写入后能读回为 files", data and data["kind"] == "files")
check("文件: 路径列表一致", [os.path.normcase(p) for p in data["files"]] ==
     [os.path.normcase(f1), os.path.normcase(f2)])

# 4. DIB 解析容错:垃圾数据不崩溃
check("容错: 非法 DIB 返回 None", clipboard_io.dib_to_png(b"\x00" * 20) is None)

print(f"\n全部通过: {passed} 项")
