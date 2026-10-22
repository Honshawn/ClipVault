# 第三方组件与许可证声明

ClipVault 本体以 MIT 许可证发布(见 `LICENSE`)。发布的可执行文件由 PyInstaller 打包,
内含以下第三方组件。各组件版权归其作者所有,按各自许可证分发。

| 组件 | 版本 | 许可证 | 项目地址 |
|---|---|---|---|
| pystray | 0.19.5 | **LGPL-3.0** | https://github.com/moses-palmer/pystray |
| Pillow | 13.0.0 | MIT-CMU (HPND) | https://github.com/python-pillow/Pillow |
| pywin32 | 312 | PSF License | https://github.com/mhammond/pywin32 |
| keyboard | 0.13.5 | MIT | https://github.com/boppreh/keyboard |
| PyInstaller (bootloader) | 6.22.3 | GPL-2.0 + 特殊例外 | https://github.com/pyinstaller/pyinstaller |
| Python | 3.13 | PSF License | https://www.python.org/ |

## pystray(LGPL-3.0)特别说明

托盘图标功能使用 pystray,该库以 **GNU Lesser General Public License v3.0** 分发,
与 ClipVault 自身的 MIT 许可证相互独立。许可证全文见 [`licenses/LGPL-3.0.txt`](licenses/LGPL-3.0.txt)。

LGPL-3.0 要求分发时允许接收者替换该库。为此:

1. pystray 的完整源码可从 https://github.com/moses-palmer/pystray 获取,任意版本可自行修改;
2. 修改后的 pystray 可放入本地 Python 环境后直接运行源码版 ClipVault
   (`pip install pystray==0.19.5` 后替换 `site-packages/pystray` 即可);
3. 打包版 exe 中的 pystray 组件可用 PyInstaller 重新打包替换——仓库已提供
   `.github/workflows/release.yml`,修改 `requirements.txt` 中的 pystray 来源后推 tag 即可得到替换版本。

## PyInstaller 说明

PyInstaller 以 GPL-2.0 附"打包例外"发布,该例外明确允许将任意许可证的程序
(含商业程序)用 PyInstaller 打包分发,打包产物不受 GPL 约束。

## Pillow / pywin32 / keyboard

- Pillow:MIT-CMU 许可证(HPND),允许商业使用与再分发,需保留版权声明。
- pywin32:Python Software Foundation License,BSD 风格。
- keyboard:MIT。

以上组件的许可证原文随各自源码仓库提供;如需在离线环境中核对,可查看
`licenses/` 目录及对应 PyPI 包的 `dist-info` 内容。
