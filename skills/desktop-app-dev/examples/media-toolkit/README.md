# Media Toolkit

Runnable tkinter demo for the media pipeline templates. It shows a live
download progress bar with percent, total file size, speed, ETA, and stage,
plus an all-format conversion tab that reads the unified format catalog
(video, audio, image, subtitle, document, data, archive).

Run:

```powershell
python examples/media-toolkit/app.py
```

No third-party Python packages are required. Media/image conversion needs
ffmpeg on `PATH`; text, subtitle, and archive conversions use the Python
standard library. The app imports `media_downloader.py`,
`file_converter.py`, and `media_formats.py` from `../scripts/` directly,
so template fixes automatically propagate to this example.
