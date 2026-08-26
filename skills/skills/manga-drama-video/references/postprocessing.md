# 极致后处理：滤镜、降噪与修复（FFmpeg / VapourSynth）

本文件用于 Step 9。Step 8 成片经用户批准后，Codex 自动生成 `postprocess_plan.json`，检测并配置 FFmpeg / VapourSynth，然后输出增强成片。

## 输出文件

- `09_final_enhanced.mp4`：无字幕增强母版。
- `09_final_enhanced_with_subs.mp4`：增强后再烧录字幕的交付版。
- `09_postprocess_report.md`：实际使用的滤镜、模型、命令和结果。
- `09_deai_check.md`：后处理后的 De-AI 最终检查。

## 后处理质量档

| profile | 用途 | 默认动作 |
| --- | --- | --- |
| light | 快速交付 | 轻降噪、轻微锐化、色彩微调 |
| balanced | 默认 | 稳定 + 降噪 + 锐化 + 色彩 + 轻颗粒 |
| extreme | 极致画质 | 去隔行、重度降噪、修复、放大、色彩分级、颗粒 |

用户可指定 `profile`，也可逐项指定 filter 和 VapourSynth 模型。用户指定后写入 `postprocess_plan.json`，禁止静默覆盖。

## FFmpeg 滤镜

| 环节 | 常用 filter | 用途 |
| --- | --- | --- |
| 防抖 | `vidstabdetect` + `vidstabtransform` | 手持抖动修复 |
| 去隔行 | `yadif` | 消除隔行扫描 |
| 降噪 | `hqdn3d` / `nlmeans` | 减少噪点和压缩块 |
| 锐化 | `unsharp` | 提升边缘清晰度 |
| 色彩 | `eq` / `colorbalance` / `curves` | 电影感调色 |
| 放大 | `scale` / `zscale` | 分辨率提升 |
| 颗粒 | `noise` | 增加自然胶片颗粒，避免过度光滑 |

## VapourSynth 插件与模型

| 能力 | 推荐组件 | 说明 |
| --- | --- | --- |
| 高质量降噪 | KNLMeansCL / BM3D | 空间+时间降噪 |
| 运动补偿降噪 | mvtools | 保留动态细节 |
| 去隔行 | QTGMC / nnedi3 | 高质量去隔行 |
| 放大修复 | Real-ESRGAN / waifu2x | 超分修复细节 |
| 补帧 | RIFE | 提高流畅度 |
| 输入输出 | ffms2 / lsmas / VapourSynth | 读取和输出视频 |

## 自动安装与配置

1. 运行 `python scripts/setup_postprocess.py <project_dir> --install-models --model-dir <dir>`。
2. 脚本会检测 `ffmpeg`、`ffprobe`、`vspipe`、VapourSynth Python 绑定和模型目录。
3. 缺少 VapourSynth 时，脚本输出 Windows / Linux 安装说明，不假装已安装。
4. `--install-models` 会从模型 registry 下载 Real-ESRGAN 等模型到 `model_dir`；下载失败会记录为 `blocked`。
5. 用户允许时，Codex 可以执行 winget/pip/安装器命令完成系统级安装；未批准前只检测和生成计划。

## `postprocess_plan.json` schema

```json
{
  "postprocess_plan_version": 1,
  "profile": "balanced",
  "enabled": true,
  "order": ["stabilize", "deinterlace", "denoise", "sharpen", "color", "upscale", "grain"],
  "filters": {
    "stabilize": {"enabled": true, "method": "vidstab", "shakiness": 5},
    "deinterlace": {"enabled": false, "method": "yadif"},
    "denoise": {"enabled": true, "method": "hqdn3d", "strength": 3},
    "sharpen": {"enabled": true, "method": "unsharp", "amount": 0.5},
    "color": {"enabled": true, "method": "eq", "params": {"saturation": 1.05, "contrast": 1.03}},
    "upscale": {"enabled": false, "method": "real-esrgan", "scale": 2, "model": "realesrgan_x4plus"},
    "grain": {"enabled": true, "method": "noise", "amount": 3}
  },
  "vapoursynth": {
    "enabled": false,
    "script": null,
    "plugins": [],
    "models": {}
  },
  "outputs": {
    "video": "09_final_enhanced.mp4",
    "video_with_subs": "09_final_enhanced_with_subs.mp4"
  }
}
```

## 规则

- 后处理必须在 Step 8 成片批准后执行，不能跳过审核直接出最终版。
- 用户指定 profile 或滤镜时，Codex 必须按用户配置执行。
- 后处理不得改变人物脸型和跨集一致性；增强后仍要跑 continuity + De-AI 检查。
- 不能为了“极致画质”把人物磨成塑料感、把轮廓修丢、把嘴型修错。
- 每次实际执行后写 `09_postprocess_report.md`，记录滤镜链、VapourSynth 脚本、模型路径和输出文件。
