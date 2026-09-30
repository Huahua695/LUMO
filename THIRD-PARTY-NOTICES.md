# 第三方组件声明 (Third-Party Notices)

拾光工具箱依赖以下优秀的开源项目。各组件版权归其原作者所有，本仓库感谢并致敬。

| 组件 | 版本 | 来源 | 许可证 | 用途 |
|---|---|---|---|---|
| N_m3u8DL-CLI | 3.0.2（本地编译） | https://github.com/nilaoda/N_m3u8DL-CLI | MIT | m3u8/HLS/MPD 下载引擎 |
| yt-dlp | 2026.8.19（PyPI） | https://github.com/yt-dlp/yt-dlp | Unlicense | 网站视频信息提取与下载 |
| Real-ESRGAN-ncnn-vulkan | v0.2.0（官方 20220424 包） | https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan | MIT | AI 超分推理引擎 |
| Real-ESRGAN 官方模型 | 20220424 包内置（x4plus / x4plus-anime / animevideov3-x2/3/4） | https://github.com/xinntao/Real-ESRGAN (releases) | MIT | 超分权重 |
| realesr-general-x4v3 权重 | 官方 v0.2.5.0 发布的 PyTorch 权重 | https://github.com/xinntao/Real-ESRGAN (releases) | MIT | 真人·通用模式（本仓库 `model_conv/convert.py` 转换为 ncnn 格式） |
| FFmpeg（含 ffprobe） | N-125953-gd3ad8a7fee（2026-08-03 构建，shared） | 随本地 N_m3u8DL-CLI 项目引入 | **GPLv3+**（构建启用 `--enable-gpl --enable-version3`） | 抽帧 / 合成 / 剪切 / 转封装 |
| ncnn | 内置于 realesrgan 引擎 | https://github.com/Tencent/ncnn | MIT | 神经网络推理框架 |
| PySide6 | 6.11.2（PyPI） | https://www.qt.io/ | LGPLv3 | 图形界面 |
| PyInstaller | 6.22.3（PyPI） | https://pyinstaller.org/ | GPL with special exception（仅构建用，不随包分发义务） | 打包 |
| Pillow | 12.3.0（PyPI） | https://python-pillow.org/ | HPND（MIT-CMU） | 图标生成 / 测试 |
| torch / numpy | PyPI（清华镜像） | https://pytorch.org / https://numpy.org | BSD-3 / MIT | 仅模型转换与测试，非运行时依赖 |

## 重要说明

1. **FFmpeg 为 GPL 构建**：本软件自身代码遵循 GPL-3.0（见 LICENSE）。若对外分发包含
   FFmpeg 的完整软件包，整个分发包需遵守 GPLv3 的相应义务（自用无任何限制）。
2. **`tools/realesrgan/models/realesr-general-x4v3.{param,bin}`** 是本仓库唯一自产的
   二进制资产：权重取自上方官方 PyTorch 发布文件（SHA256 校验见 `docs/审计报告.md`），
   由 `model_conv/convert.py` 转换，转换正确性以官方 animevideov3 权重逐字节重建官方
   发布 bin 作为金标准验证。
3. PySide6 以动态链接方式使用，符合 LGPLv3 的义务要求；如替换为静态链接需重新评估。
4. 各组件的完整许可证文本以各上游仓库为准。
