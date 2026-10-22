@echo off
REM ClipVault 打包脚本:产出 dist\ClipVault.exe(单文件、无控制台窗口)
REM 前置:① 在项目目录创建 .venv 并 pip install -r requirements.txt
REM      ② 可选:下载 UPX(https://github.com/upx/upx/releases)解压到 tools\upx\upx.exe 可进一步压缩体积
setlocal
if exist "%~dp0.venv\Scripts\pyinstaller.exe" (
    set PYI="%~dp0.venv\Scripts\pyinstaller.exe"
) else (
    set PYI=pyinstaller
)
set UPX_ARG=
if exist "%~dp0tools\upx\upx.exe" set UPX_ARG=--upx-dir "%~dp0tools\upx"

%PYI% --noconfirm --clean --onefile --noconsole --name ClipVault %UPX_ARG% ^
    --exclude-module tkinter.test --exclude-module test ^
    --exclude-module unittest --exclude-module doctest ^
    --exclude-module pydoc --exclude-module setuptools ^
    main.py
echo.
echo 产物: dist\ClipVault.exe
pause
