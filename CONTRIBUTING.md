# 贡献指南

感谢关注拾光工具箱！欢迎 Issue 报告问题与 PR 贡献代码。

## 开发环境

1. Windows 10/11 + 支持 Vulkan 的显卡（真机测试 GPU 功能需要）
2. Python 3.12+：
   ```bash
   python -m venv venv
   venv/Scripts/python -m pip install -r requirements.txt -r requirements-dev.txt
   ```
3. 外部工具（`tools/` 目录不入库，需自备，来源见 `THIRD-PARTY-NOTICES.md`）：
   - `N_m3u8DL-CLI.exe`（可从上游 release 下载，或本地编译）
   - `ffmpeg.exe` / `ffprobe.exe` + 同目录 7 个 `av*/sw*` DLL（shared 构建必须带 DLL）
   - `realesrgan/realesrgan-ncnn-vulkan.exe` + `vcomp140*.dll` + `models/`（官方 20220424 包）
4. 生成通用模式模型：`venv/Scripts/python model_conv/convert.py`

## 提交前检查

```bash
# 1) 全部自动化测试通过（15 项）
QT_QPA_PLATFORM=offscreen venv/Scripts/python tests/test_suite.py

# 2) 打包产物深度自检通过
venv/Scripts/python scripts/build_app.py
QT_QPA_PLATFORM=offscreen "dist/拾光工具箱/拾光工具箱.exe" --selftest && echo OK
```

## 约定

- 提交信息用中文或英文均可，一行主题 + 必要时的正文说明「为什么改」
- 新功能必须附带测试；修复 bug 的 PR 请附上能复现问题的最小用例
- 涉及外部工具交互（子进程参数、输出解析）的改动请在 PR 描述中注明验证过的环境
  （显卡型号 / 驱动版本），便于多硬件复验
- 不要把 `tools/`、`dist/`、`venv/`、模型 `.pth/.bin` 等大文件提交进仓库（.gitignore 已配置）
- UI 文案使用简体中文，保持「对新手友好」的语气

## 报告 Bug

请附上：Windows 版本、显卡型号与驱动版本、软件版本（设置页可见）、复现步骤、
任务输出目录中的 `.sgjob_*.json` 内容（若涉及断点续跑问题，注意隐去个人路径）。
