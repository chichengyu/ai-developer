# FFmpeg / VapourSynth 自动安装流程

当用户说“自动安装”“解放双手”“AI 全程处理”时，Codex 使用 `scripts/install_ffmpeg_vapoursynth.py` 自动检测系统、安装依赖、下载模型和插件，并写安装报告。用户只需要在系统级安装前授权一次，之后不再手动操作。

## 自动安装范围

- FFmpeg / ffprobe
- VapourSynth 核心
- VapourSynth 常用插件：KNLMeansCL、mvtools、nnedi3
- Real-ESRGAN 等画质模型
- 环境变量/PATH 检测与报告

## 图片引擎自动安装

- Step 5 默认使用当前模型/API；当前模型缺图片能力时调用 Codex imagegen skill/MCP；本地 ComfyUI / SD WebUI API 仅在用户明确选择本地模式时检测。
- 无任何图片引擎且用户明确选择本地模式时，才运行 `python scripts/install_image_engine.py --auto-install --start`，默认自动安装 diffusers + RealVisXL 写实模型 + PyTorch + Pillow/OpenCV 图片处理依赖；也可用 `--engine comfyui` 安装 ComfyUI。
- 国内网络建议设置 `PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/`，PyTorch 可通过 `TORCH_WHEELS_DIR` 指定本地 cu128 wheels，避免官方源超时。
- 安装完成后再生参考图和分镜图；禁止要求用户复制提示词到即梦 AI 等外部网站生成图片再放回。
- 本地引擎生成图片统一调用 `scripts/generate_images.py`，锁定 seed 和人物 prompt fragment。
- 生成后的图片由 `scripts/process_image_assets.py` 本地统一尺寸、降噪、锐化。

### IPAdapter 多参考节点

当本地模式需要默认 SDXL 生图真正吃 9 图参考时：

```powershell
python scripts/install_image_engine.py --install-ref-nodes
```

该命令安装 `ComfyUI_IPAdapter_plus` 节点；还需要 ComfyUI 的 IPAdapter SDXL 模型与 CLIP Vision 模型才能真正生效。模型缺失时，`generate_images.py` 会提示参考未生效，或改用包含 `{ref_image_1..9}` / `{reference_grid}` 占位符的自定义 `video_workflow.json`，禁止静默忽略参考。

## 视频引擎自动安装

当用户明确选择本地模式且项目需要真实动态镜头时，Codex 才使用 `scripts/install_video_engine.py` 自动检测硬件并补齐本地软件和模型：

```powershell
python scripts/install_video_engine.py <project_dir> --auto
```

`--auto` 会按当前硬件自动完成：

- 缺少 FFmpeg/ffprobe 时先安装 FFmpeg。
- 缺少 ComfyUI 时先安装本地 ComfyUI 图片/视频引擎。
- 下载 Wan 2.1 480P 模型、T5/UMT5 文本编码器、VAE、CLIP Vision，用于高质量成片。
- 下载 LTX-Video 2B 模型和 T5 XXL 文本编码器，用于 8GB 显存的快速迭代；显存低于 12GB 时优先下载 fp8 编码器。
- 安装 VideoHelperSuite、LivePortrait 等视频与口型节点。
- 启动 `http://127.0.0.1:8188` 并把硬件检测结果写入 `video_engine_report.json`。

也可以单独安装某一类模型：

```powershell
python scripts/install_video_engine.py <project_dir> --install --models wan
python scripts/install_video_engine.py <project_dir> --install --models ltx
python scripts/install_video_engine.py <project_dir> --install --models liveportrait
```

LTX 使用 ComfyUI 内置节点，不需要额外克隆 GitHub 插件；模型文件放在 `models/checkpoints/`，文本编码器放在 `models/text_encoders/`。

### Wav2Lip 音频驱动口型

说话镜头需要真正的音频驱动口型，且用户明确选择本地模式时：

```powershell
python scripts/install_video_engine.py <project_dir> --install --models wav2lip
```

该命令会把 Wav2Lip 代码安装到 `E:\soft\manga-drama-video\wav2lip`（或当前平台默认运行时目录），下载 `wav2lip.pth` 与 `s3fd.pth`，并安装推理依赖。安装脚本会自动打上兼容补丁：适配新版 librosa/numba 的音频特征提取，并绕过新版 OpenCV 无法写视频的缺陷，改为逐帧写入用户输出目录后用 FFmpeg 合成。`lip_sync.py --engine wav2lip --require-audio-sync` 会自动把静态关键帧转成临时视频、用音频驱动嘴型，再把原音频合并回成片。

## Windows

1. FFmpeg：优先 `winget install Gyan.FFmpeg`，失败时尝试 `choco install ffmpeg -y` 或 `scoop install ffmpeg`。
2. VapourSynth：通过 GitHub API 获取官方最新 Windows x64 安装包，下载后执行静默安装。
3. 插件：从各插件官方 GitHub Releases 下载 DLL，解压到 VapourSynth 插件目录。
4. 模型：从 Real-ESRGAN 官方 Releases 下载到模型目录。
5. 安装后检测 `ffmpeg`、`ffprobe`、`vspipe`，把实际路径写入 `install_report.json`。

## Linux / macOS

- Debian/Ubuntu：`sudo apt-get install -y ffmpeg vapoursynth`
- Arch：`sudo pacman -S --noconfirm ffmpeg vapoursynth`
- macOS：`brew install ffmpeg vapoursynth`

插件和模型仍需按平台下载 DLL / `.so` / `.pth`，脚本会检测并报告。

## 执行流程

1. Codex 先向用户确认：`是否允许自动安装系统级依赖？`
2. 用户批准后运行：
   ```powershell
   python scripts/install_ffmpeg_vapoursynth.py <project_dir> --auto-install
   ```
3. 脚本生成 `install_report.json` 和 `09_install_report.md`。
4. 安装成功后继续 `setup_postprocess.py` 和 `postprocess.py`，全程无需用户再操作。
5. 安装失败时停止 Step 9，报告失败命令和原因，不假装成功。

## 安全规则

- 只在用户明确要求自动安装时执行系统级命令。
- 只从官方 GitHub Releases、winget/choco/scoop、系统包管理器下载。
- 不执行卸载、清理或任何破坏性命令。
- UAC 授权是系统安全要求；出现 UAC 时让用户点一次“允许”，其余步骤自动完成。
