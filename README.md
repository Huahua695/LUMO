# 拾光工具箱 (ShiGuang Toolbox / LUMO)

<p align="center">
  <img src="assets/icon.png" width="140" alt="LUMO">
</p>

> 轻量、简洁、可视化的桌面媒体工具箱：**资源无损下载 · AI 画质增强 · 视频剪切**。
> 全部处理在本机完成，不上传任何数据，拔网线也能用。

一个为新手设计的 Windows 桌面应用（PySide6），把 m3u8 下载、网站视频下载、文件直链下载、
AI 超分辨率（图片/视频）和视频剪切整合进一个干净的界面里，并支持**任务断点续跑**——
增强一个长视频的中途，关机、睡眠、崩溃都不怕，下次打开点一下「恢复任务」接着算。

> 仓库地址：https://github.com/Huahua695/LUMO

---

## ✨ 功能总览

### ⬇️ 下载
粘贴链接即可，自动识别类型并选择引擎：

| 链接类型 | 例子 | 引擎 |
|---|---|---|
| 视频网站链接 | B站 / YouTube / X 等（yt-dlp 收录的站点） | 内置 [yt-dlp](https://github.com/yt-dlp/yt-dlp) |
| 抖音（含分享口令短链） | `v.douyin.com/xxx`、`douyin.com/jingxuan?modal_id=…` | 自建解析：**无水印** 1080p，无需登录 |
| m3u8 / HLS / MPD（含直播源） | `.../index.m3u8` | 内置 [N_m3u8DL-CLI](https://github.com/nilaoda/N_m3u8DL-CLI)（AES-128 自动解密、自动合并） |
| 文件直链 | 以 `.mp4 .mp3 .jpg` 等结尾的网址 | 内置下载器：原始字节保存，**天然无损**，支持 HTTP Range **断点续传** |

**站点兼容性（实测口径）**：

| 站点 | 免配置 | 需要什么 |
|------|--------|----------|
| B站 | ✅ 可下 | 高清 / 大会员画质需 Cookie（设置 → Cookie） |
| 抖音 | ✅ 无水印 | 私密 / 好友可见 / 审核中的作品不可下 |
| YouTube / X | ❌ | 代理（设置 → 网络，支持跟随系统代理） |
| 西瓜 / 小红书 | ❌ | Cookie |
| 快手 / 好看视频 / 微博 | ❌ | yt-dlp 未收录或上游 bug，暂无解 |

- **可选画质/分辨率**：最佳 / 1080p / 720p / 480p / 仅音频（网站视频）
- **可选保存格式**：MP4 / MKV / MP3 / M4A / JPG / PNG——按链接类型动态给出；
  直链的格式转换是下载后自动后处理（视频无损转封装、音频提取、图片转格式），
  转换失败自动保留原始文件
- **批量粘贴**：一次粘贴多个 URL（或含链接的整段文字），自动提取、去重、排队下载
- 保存位置自由选择，最多同时 3 个任务，可取消
- **任务运行期间自动阻止系统睡眠**

### ✨ 画质增强
基于 [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)（ncnn + Vulkan），**Intel / AMD / NVIDIA 显卡通吃**（核显可用，无需 CUDA），三种模式：

| 内容 | 模式 | 模型 |
|---|---|---|
| 风景/人像/截图 2/3/4 倍 | 照片模式 | realesrgan-x4plus |
| 动漫图片 | 动漫·动画模式 | realesrgan-x4plus-anime |
| **动漫视频 2/3/4 倍** | 动漫·动画模式 | realesr-animevideov3（快速视频模型） |
| **真人照片 2/3/4 倍** | 真人·通用模式 | realesr-general-x4v3 |
| **真人视频 固定 2 倍**（速度考虑） | 真人·通用模式 | realesr-general-x4v3 |

- 拖拽批量处理，图片视频可混合
- **断点续跑**：视频增强失败 / 取消 / 重启电脑后进度自动保留，重新打开软件会出现
  「🔄 恢复任务」横幅，点一下从断点继续（已完成的帧用硬链接跳过，零重复计算）
- 视频流水线：ffmpeg 抽帧 → AI 逐帧超分 → 合成（音频原样拷贝，不重编码）
- 实测速度参考（Intel Arc 130T 核显）：动漫视频约 4 帧/秒（720p 输出）；通用模型图片
  4x（960×540→4K）约 1.5 秒

### ✂️ 视频剪切 / 音频提取
拖入视频 → 播放预览打点（或直接输入 `01:23.50` 这样的时间）→ 两种输出：

- **剪切视频**：精确剪切（H.264 CRF17 重新编码，帧级准确）或无损剪切（流复制秒出，按关键帧对齐）
- **提取音频**：把本地视频（如已下载的 MP4）提取为 **MP3 / M4A**，支持全片或只取某一段；
  网站链接则直接在下载页选「仅音频 / MP3」一步到位

## 📦 安装

### 普通用户

从 **Releases** 下载 `拾光工具箱-vX.Y.Z.zip`，解压到任意位置，双击「拾光工具箱.exe」即可。
无需安装 Python 或任何运行环境。

> 发行包使用 LZMA 压缩（体积更小）。Windows 11 可直接右键「全部解压缩」；
> **Windows 10 用户请改用 [7-Zip](https://www.7-zip.org/) 或 Bandizip 解压**，
> 系统自带的资源管理器可能无法识别。

> 首次运行如被 SmartScreen 提示，选择「仍要运行」；本软件不写注册表、不后台驻留、不上传数据。

### 系统要求

- Windows 10 / 11（x64）
- 支持 Vulkan 的显卡（近十年的 Intel 核显 / AMD / NVIDIA 均可），建议更新显卡驱动

### 从源码构建

```bash
git clone <本仓库地址>
cd newvideo

# 1) Python 环境
python -m venv venv
venv/Scripts/python -m pip install -r requirements.txt -r requirements-dev.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2) 准备外部工具（见 docs/审计报告.md 第二节的来源清单）
#    tools/ 目录结构：
#    tools/N_m3u8DL-CLI.exe
#    tools/ffmpeg.exe tools/ffprobe.exe + av*.dll sw*.dll
#    tools/realesrgan/realesrgan-ncnn-vulkan.exe + vcomp140*.dll + models/（官方包内全部模型）
#
# 3) 生成真人·通用模式模型（需要 torch，只在转换时使用）
venv/Scripts/python model_conv/convert.py

# 4) 运行（app 已是包，等价：python -m app.main）
venv/Scripts/python run.py

# 5) 打包（自动拷贝 tools 并创建桌面快捷方式）
venv/Scripts/python scripts/build_app.py
```

## 🧪 测试

```bash
QT_QPA_PLATFORM=offscreen venv/Scripts/python tests/test_suite.py
```

33 项自动化测试：单元测试（工具函数 / URL 识别 / 模型方案表 / 防睡眠 / 任务档案
含 running 态可恢复 / m3u8 兜底名 / 帧完整性校验）+ 集成测试（Range 续传下载、
两种剪切模式、GPU 图片增强、**视频增强中断→恢复全流程**、抽帧中断恢复）。
详见 [docs/测试报告.md](docs/测试报告.md)。

## 🏗️ 工作原理

```
下载：URL ──识别──▶ yt-dlp / N_m3u8DL-CLI / 内置直链下载器 ──▶ 原始字节落盘（无损）

增强：视频 ──ffmpeg 抽帧──▶ 每帧图片 ──realesrgan-ncnn-vulkan(Vulkan)──▶ 高清帧
            ──ffmpeg 合成──▶ 高清视频（音频原样拷贝）
      中断时：任务档案(.sgjob_*.json) + 已完成帧(.sgtmp_*)保留在输出目录，
            恢复时硬链接未完成帧增量推理，成品合成后自动清理现场

剪切：ffmpeg -ss/-t 精确重编码（libx264 crf17）或 -c copy 流复制
```

推理引擎为腾讯 [ncnn](https://github.com/Tencent/ncnn) 框架的 Vulkan 后端，模型文件即
`tools/realesrgan/models/` 下的 `.param/.bin`，无 Python/CUDA 依赖。其中
`realesr-general-x4v3` 官方只发布了 PyTorch 权重，本仓库 `model_conv/convert.py`
将其转换为旧版 ncnn 格式，转换器以「官方 animevideov3 权重重建官方 bin 逐字节一致」
作为金标准验证——这也是本仓库唯一自产的二进制资产。

## 📁 项目结构

```
newvideo/
├── run.py              开发/打包入口（python -m app.main 等价）
├── app/                主程序源码（PySide6，四页：下载/增强/剪切/设置）
│   ├── main.py             包内入口（--selftest 自检模式）
│   ├── widgets.py          共用组件（卡片/目录行/空态/任务行）
│   ├── range_slider.py     剪切页双柄选区条
│   ├── douyin.py           抖音解析（短链展开/ttwid/分享页/无水印直链）
│   ├── errors.py           全界面中文报错翻译层
│   ├── proc.py             子进程常量 + stderr 滚动日志
│   ├── main_window.py      主窗口（侧边栏导航）
│   ├── download_tab.py / enhance_tab.py / cut_tab.py / settings_tab.py
│   ├── direct_dl.py        直链下载（Range 断点续传）
│   ├── m3u8_dl.py          N_m3u8DL-CLI 封装
│   ├── ytdlp_dl.py         yt-dlp Python API 封装
│   ├── enhance.py          超分流水线（图片/视频/断点续跑）
│   ├── cut_engine.py       剪切引擎
│   ├── sleep_guard.py      任务运行期阻止系统睡眠
│   └── base_task.py        任务线程基类（统一信号/取消/防睡眠）
├── model_conv/         general-x4v3 模型转换器（含官方权重逐字节验证）
├── scripts/            make_icon.py（图标）/ build_app.py（打包+快捷方式）
├── tests/              test_suite.py 自动化测试套件
├── docs/               测试报告 / 审计报告
├── tools/              外部工具（不入库，见上方构建说明）
└── dist/               打包产物（不入库）
```

## ❓ 常见问题

**Q：超分引擎报“显卡驱动不支持 Vulkan”或输出黑图？**
更新 Intel/AMD/NVIDIA 官方驱动到最新版本。核显用户建议同时把 Windows 电源计划设为「高性能」。

**Q：视频增强中途关机/重启会丢失进度吗？**
不会。进度帧和任务档案保留在输出目录（`.sgtmp_*` / `.sgjob_*.json`），重新打开软件点「恢复任务」即可。
唯一不能续的是 m3u8 下载（引擎限制）和彻底删除输出目录。

**Q：无损剪切为什么切点不准确？**
流复制只能从关键帧开始，这是视频格式的本质限制。需要帧级准确请用「精确剪切」。

**Q：为什么真人视频用通用模型比动漫视频慢？**
通用模型内部按 4 倍放大再精细缩回目标倍数；动漫快速模型（animevideov3）架构更轻。
真人内容请务必用「真人·通用模式」而不是照片模式（后者是慢工细活的 x4plus，视频会非常慢）。

**Q：数据会上传吗？**
不会。下载行为本身访问目标网站，AI 增强完全离线，无遥测、无上报。

## 🤝 贡献

欢迎 Issue 和 PR！请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。
提交前请确保 `tests/test_suite.py` 全部通过。

## ⚠️ 免责声明

本工具仅供**个人学习与研究**使用。请遵守所在地区的版权法律以及各平台的服务条款，
不要下载、传播受版权保护的内容。开发者不对任何滥用行为负责。
视频解析功能仅读取平台公开展示的信息（标题/封面/可用画质），不绕过任何付费或权限限制。

## 📄 许可证与致谢

本项目代码采用 **[GPL-3.0](LICENSE)** ——选择该许可证是为了与随包分发的 GPL 版 FFmpeg
保持一致。第三方组件清单（来源、版本、许可证、哈希）见
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)，向这些优秀的开源项目致敬：

- [N_m3u8DL-CLI](https://github.com/nilaoda/N_m3u8DL-CLI) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) ·
  [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) · [ncnn](https://github.com/Tencent/ncnn) ·
  [FFmpeg](https://ffmpeg.org) · [PySide6](https://www.qt.io/) ·
  [PyInstaller](https://pyinstaller.org/)

---

版本历史见 [CHANGELOG.md](CHANGELOG.md)。
