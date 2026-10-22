# 安全说明

## 数据存储

- 剪贴板历史(文本/图片/文件路径)以明文保存在 `%APPDATA%\ClipVault\`
- 仅存本机,不上传、不同步、不联网(全部代码无网络调用,可用 `grep -r "requests\|urllib\|socket" .` 自证)
- 清除数据:程序内"清空历史",或直接删除 `%APPDATA%\ClipVault\` 目录

## 权限说明

- 全局键盘钩子仅用于"双击 Ctrl"手势判定,不记录按键、不写入磁盘
- 不请求管理员权限。代价是无法向提权窗口注入粘贴(Windows UIPI 限制),这是有意取舍

## 敏感内容提醒

剪贴板会包含密码管理器输出、验证码、私钥等敏感内容。使用前请知悉:**本工具默认记录一切复制内容**。
如需规避:复制敏感内容后立即"清空历史";或修改 `config.py` 中 `MAX_ITEMS` 缩短留存窗口。

## 报告漏洞

**请优先使用 GitHub 私密漏洞报告**,不要在公开 Issue 里贴复现细节或敏感数据:

https://github.com/Honshawn/ClipVault/security/advisories/new

- 适用版本:当前 `main` 分支与最新 Release
- 期望响应:7 天内确认收到,30 天内给出修复计划或说明
- 修复发布后会在 Release Notes 与 Advisory 中致谢(除非你要求匿名)
- 非安全类问题(功能建议、使用疑问)请走公开 Issue
