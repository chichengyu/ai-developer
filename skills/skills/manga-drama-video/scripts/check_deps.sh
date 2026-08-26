#!/usr/bin/env bash
# Check that the runtime has the tools the manga-drama-video skill needs.
# Windows users can run `python scripts/check_deps.py` instead.
# Exit code 0 = all required tools present; 1 = at least one missing.
set -u

ok() { printf "  OK    %s\n" "$1"; }
miss() { printf "  MISS  %s (%s)\n" "$1" "$2"; }
have() { command -v "$1" >/dev/null 2>&1; }

fail=0

echo "Required"
if have ffmpeg; then ok "ffmpeg"; else miss "ffmpeg" "install via apt/brew/winget/choco"; fail=1; fi
if have ffprobe; then ok "ffprobe"; else miss "ffprobe" "ships with ffmpeg"; fail=1; fi
if have python3; then ok "python3"; else miss "python3" "needed by probe_durations.py / validate_outputs.py"; fail=1; fi
if have python && ! have python3; then ok "python (as python3)"; fi

echo
echo "Optional (improves quality)"
if have edge-tts; then ok "edge-tts (local TTS)"; else miss "edge-tts" "pip install edge-tts"; fi
if have espeak-ng || have espeak; then ok "espeak (local TTS fallback)"; fi
if have bc; then ok "bc (for time math)"; fi

echo
echo "Imagegen / talking-head providers"
if [ -n "${OPENAI_API_KEY:-}" ]; then ok "OPENAI_API_KEY set (imagegen + TTS reachable)"; else miss "OPENAI_API_KEY" "needed for OpenAI imagegen / TTS"; fi
if have curl; then ok "curl"; else miss "curl" "needed for HeyGen / D-ID / ElevenLabs API calls"; fi
if command -v liveportrait >/dev/null 2>&1 || command -v sadtalker >/dev/null 2>&1; then ok "talking-head CLI"; else miss "talking-head CLI" "install LivePortrait / SadTalker locally"; fi

if [ "$fail" -eq 0 ]; then
  echo
  echo "All required tools present."
  exit 0
else
  echo
  echo "Some required tools are missing. Step 8 (composition) and parts of Step 6 / 7 will not work until they are installed."
  exit 1
fi
