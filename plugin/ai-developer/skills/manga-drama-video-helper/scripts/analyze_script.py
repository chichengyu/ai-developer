#!/usr/bin/env python3
"""Automated deep analysis for the approved script.

Usage:
    python analyze_script.py <project_or_episode_dir>
      [--script scripts/02_script.md]
      [--output-json scripts/03_deep_analysis.json]
      [--output-md scripts/03_deep_analysis.md]
      [--dry-run]

Reads (helper layout, falls back to the flat layout used by manga-drama-video):
  <dir>/scripts/02_script.json or scripts/02_script.md
  <dir>/scripts/02_character_analysis.md (optional)
  <dir>/character-bible.md (or <series-root>/character-bible.md for series)
  <dir>/scene-bible.md (or <series-root>/scene-bible.md for series)
  <dir>/manifest.json (helper) or <dir>/00_meta.json (main skill)

Writes (helper layout):
  <dir>/scripts/03_deep_analysis.json
  <dir>/scripts/03_deep_analysis.md

The analyzer is deterministic and fully automatic: it extracts the script's
scene/shot structure, enriches character personality, behavior, appearance,
scene music, wind/grass/snow/rain environment dynamics, transitions, and
shot-level image/motion prompt hints without asking the user to fill a form.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


EMOTION_PROFILES: Dict[str, Dict[str, Any]] = {
    "weary": {
        "personality": ["高负荷", "克制", "习惯性压抑情绪", "对善意仍有反应"],
        "mood": "疲惫压抑",
        "lighting": "低照度冷调，柔和顶光，少量暖色轮廓",
        "music": {
            "bgm_mood": "疲惫钢琴",
            "tempo_bpm": "60-70",
            "instruments": ["piano", "soft strings"],
            "intensity_curve": [{"t": 0.0, "level": 0.25}, {"t": 0.5, "level": 0.35}, {"t": 1.0, "level": 0.4}],
        },
    },
    "tense": {
        "personality": ["警觉", "压抑", "环境压力大", "随时准备行动"],
        "mood": "紧张压迫",
        "lighting": "低角度硬光，冷色为主，阴影切割强烈",
        "music": {
            "bgm_mood": "悬疑低鸣",
            "tempo_bpm": "80-90",
            "instruments": ["low drone", "sub bass", "ticking percussion"],
            "intensity_curve": [{"t": 0.0, "level": 0.5}, {"t": 0.5, "level": 0.7}, {"t": 1.0, "level": 0.9}],
        },
    },
    "curious": {
        "personality": ["观察力强", "容易被细节吸引", "温和试探"],
        "mood": "好奇微妙",
        "lighting": "混合光源，霓虹/窗光带层次，主体受光清晰",
        "music": {
            "bgm_mood": "轻巧探索",
            "tempo_bpm": "70-80",
            "instruments": ["plucks", "celesta", "soft pads"],
            "intensity_curve": [{"t": 0.0, "level": 0.3}, {"t": 0.5, "level": 0.45}, {"t": 1.0, "level": 0.5}],
        },
    },
    "torn": {
        "personality": ["内心拉扯", "谨慎", "善良但自我怀疑"],
        "mood": "犹豫拉扯",
        "lighting": "冷暖交界，人物面部半明半暗",
        "music": {
            "bgm_mood": "犹豫弦乐",
            "tempo_bpm": "65-75",
            "instruments": ["cello", "piano", "air"],
            "intensity_curve": [{"t": 0.0, "level": 0.35}, {"t": 0.5, "level": 0.5}, {"t": 1.0, "level": 0.45}],
        },
    },
    "tender": {
        "personality": ["温柔", "共情", "主动付出"],
        "mood": "温柔治愈",
        "lighting": "暖色主光，柔焦边缘，轻微逆光",
        "music": {
            "bgm_mood": "温柔钢琴",
            "tempo_bpm": "55-65",
            "instruments": ["piano", "cello", "soft room tone"],
            "intensity_curve": [{"t": 0.0, "level": 0.2}, {"t": 0.5, "level": 0.35}, {"t": 1.0, "level": 0.3}],
        },
    },
    "soft": {
        "personality": ["平静", "包容", "愿意接近"],
        "mood": "柔软安定",
        "lighting": "大面积柔光，低反差，肤质自然",
        "music": {
            "bgm_mood": "柔软氛围",
            "tempo_bpm": "60-70",
            "instruments": ["warm pad", "acoustic guitar", "breath"],
            "intensity_curve": [{"t": 0.0, "level": 0.25}, {"t": 0.5, "level": 0.3}, {"t": 1.0, "level": 0.25}],
        },
    },
    "warm": {
        "personality": ["外冷内热", "情感被唤起", "愿意承担"],
        "mood": "温暖释然",
        "lighting": "暖金色调，逆光轮廓，眼睛有高光",
        "music": {
            "bgm_mood": "温暖渐进",
            "tempo_bpm": "65-75",
            "instruments": ["acoustic guitar", "piano", "warm strings"],
            "intensity_curve": [{"t": 0.0, "level": 0.3}, {"t": 0.5, "level": 0.5}, {"t": 1.0, "level": 0.65}],
        },
    },
    "hopeful": {
        "personality": ["内敛", "需要被唤醒的乐观", "坚定向前"],
        "mood": "希望上扬",
        "lighting": "晨光/暖阳，天空层次，人物轮廓清晰",
        "music": {
            "bgm_mood": "希望弦乐",
            "tempo_bpm": "70-80",
            "instruments": ["strings build", "piano", "soft drums"],
            "intensity_curve": [{"t": 0.0, "level": 0.3}, {"t": 0.5, "level": 0.6}, {"t": 1.0, "level": 0.8}],
        },
    },
    "angry": {
        "personality": ["冲动", "强烈目的性", "边界感强"],
        "mood": "愤怒爆发",
        "lighting": "硬光，暖色危险感，高反差",
        "music": {
            "bgm_mood": "爆发鼓点",
            "tempo_bpm": "110-120",
            "instruments": ["drums", "brass", "punchy bass"],
            "intensity_curve": [{"t": 0.0, "level": 0.5}, {"t": 0.5, "level": 0.9}, {"t": 1.0, "level": 0.8}],
        },
    },
    "fearful": {
        "personality": ["敏感", "防御", "脆弱"],
        "mood": "恐惧不安",
        "lighting": "暗部扩大，冷蓝恐怖感，光源闪烁",
        "music": {
            "bgm_mood": "惊悚细碎",
            "tempo_bpm": "90-100",
            "instruments": ["string tremolo", "clock ticks", "sub drone"],
            "intensity_curve": [{"t": 0.0, "level": 0.4}, {"t": 0.5, "level": 0.75}, {"t": 1.0, "level": 0.95}],
        },
    },
    "sad": {
        "personality": ["敏感", "内敛", "需要情感出口"],
        "mood": "低沉伤感",
        "lighting": "冷调柔光，逆光下的人物剪影",
        "music": {
            "bgm_mood": "悲伤钢琴",
            "tempo_bpm": "50-60",
            "instruments": ["piano", "solo violin", "silence"],
            "intensity_curve": [{"t": 0.0, "level": 0.2}, {"t": 0.5, "level": 0.4}, {"t": 1.0, "level": 0.35}],
        },
    },
    "calm": {
        "personality": ["沉着", "稳定", "观察优先"],
        "mood": "平静稳定",
        "lighting": "均匀自然光，低反差，空间层次清楚",
        "music": {
            "bgm_mood": "安静氛围",
            "tempo_bpm": "60-70",
            "instruments": ["pads", "room tone", "light piano"],
            "intensity_curve": [{"t": 0.0, "level": 0.2}, {"t": 0.5, "level": 0.25}, {"t": 1.0, "level": 0.2}],
        },
    },
    "excited": {
        "personality": ["高能量", "外向", "行动力强"],
        "mood": "兴奋高能",
        "lighting": "高饱和霓虹/舞台光，快速光斑",
        "music": {
            "bgm_mood": "高能电子",
            "tempo_bpm": "120-130",
            "instruments": ["synth", "four-on-floor drums", "bass"],
            "intensity_curve": [{"t": 0.0, "level": 0.6}, {"t": 0.5, "level": 0.8}, {"t": 1.0, "level": 0.9}],
        },
    },
}

DEFAULT_EMOTION_PROFILE: Dict[str, Any] = {
    "personality": ["根据剧情推进持续变化", "行为受环境和目标驱动"],
    "mood": "中性叙事",
    "lighting": "自然电影光，主体清晰，背景有层次",
    "music": {
        "bgm_mood": "叙事氛围",
        "tempo_bpm": "65-80",
        "instruments": ["piano", "strings", "ambient pad"],
        "intensity_curve": [{"t": 0.0, "level": 0.3}, {"t": 0.5, "level": 0.45}, {"t": 1.0, "level": 0.5}],
    },
}

BEHAVIOR_KEYWORDS: List[Tuple[Tuple[str, ...], str]] = [
    (("蹲下", "弯腰", "伸手", "靠近", "squat", "reach"), "主动接近与帮助"),
    (("发现", "看见", "听到", "寻找", "notice", "spot"), "观察和探索"),
    (("犹豫", "停顿", "迟疑", "hesitate"), "权衡与停顿"),
    (("抱起", "抱住", "扶起", "牵住", "抱走", "pick up"), "承担与保护"),
    (("拔剑", "挥剑", "斩", "刺", "格挡", "闪身", "slashing", "strike"), "战斗与攻防"),
    (("奔跑", "追赶", "逃走", "冲出", "run", "chase"), "快速移动"),
    (("脱下", "披上", "裹住", "take off", "wrap"), "照顾与付出"),
    (("微笑", "笑", "哭", "低头", "抬头", "smile"), "情绪外化"),
]

SHOT_TYPE_CYCLE = ["wide", "medium", "close-up", "insert"]
CAMERA_CYCLE = ["static", "push-in", "pan-L", "medium", "pull-back", "orbit"]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def clean_value(value: str) -> str:
    return value.strip().strip('"').strip("'")


def load_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        return json.loads(read_text(path))
    except (json.JSONDecodeError, OSError):
        return None


def slugify(value: str, fallback: str = "char") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff_-]+", "-", value).strip("-")
    return cleaned or fallback


def split_sections(text: str) -> List[Tuple[str, str]]:
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", text))
    sections: List[Tuple[str, str]] = []
    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections.append((title, text[match.end():end].strip()))
    return sections


def split_title(title: str) -> Tuple[str, Optional[str]]:
    parts = re.split(r"\s*[—\-–]\s*", title, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    tokens = title.split()
    if len(tokens) >= 2:
        return tokens[0].strip(), " ".join(tokens[1:]).strip()
    return title, None


def parse_bullet_kv(body: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for line in body.splitlines():
        match = re.match(r"^\s*[-*]\s*([^:：]+?)\s*[:：]\s*(.+?)\s*$", line)
        if match:
            result[match.group(1).strip()] = match.group(2).strip()
    return result


def parse_character_bible(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for title, body in split_sections(read_text(path)):
        cid, name = split_title(title)
        if not cid:
            continue
        item: Dict[str, Any] = {"character_id": cid, "name": name or cid}
        kv = parse_bullet_kv(body)
        for line in body.splitlines():
            if line.lstrip().startswith("-") or line.lstrip().startswith("#"):
                continue
            yaml_match = re.match(r"^\s*([a-zA-Z_]+):\s*(.*?)\s*$", line)
            if yaml_match:
                kv[yaml_match.group(1)] = yaml_match.group(2)
        item["name"] = kv.get("name") or name or cid
        item["role"] = kv.get("role", "supporting")
        item["seed"] = kv.get("seed") or kv.get("seed_id")
        item["voice_id"] = kv.get("voice_id")
        item["appearance"] = {
            "face": kv.get("脸型", ""),
            "hair": kv.get("发型", ""),
            "body": kv.get("体型", ""),
            "costume": kv.get("服装", ""),
            "props": kv.get("常驻道具", ""),
        }
        item["prompt_fragment"] = kv.get("Prompt fragment", "")
        result[cid] = item
    return result


def parse_character_analysis(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for title, body in split_sections(read_text(path)):
        cid, name = split_title(title)
        if not cid:
            continue
        kv = parse_bullet_kv(body)
        result[cid] = {
            "name": name or cid,
            "episode_goal": kv.get("episode_goal", ""),
            "emotional_arc": kv.get("emotional_arc", ""),
            "actions": kv.get("actions", ""),
            "wardrobe_state": kv.get("wardrobe_state", ""),
            "voice_tone": kv.get("voice_tone", ""),
            "continuity_notes": kv.get("continuity_notes", ""),
        }
    return result


def parse_scene_bible(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for title, body in split_sections(read_text(path)):
        sid, name = split_title(title)
        if not sid:
            continue
        kv = parse_bullet_kv(body)
        for line in body.splitlines():
            if line.lstrip().startswith("-") or line.lstrip().startswith("#"):
                continue
            yaml_match = re.match(r"^\s*([a-zA-Z_]+):\s*(.*?)\s*$", line)
            if yaml_match:
                kv[yaml_match.group(1)] = yaml_match.group(2)
        result[sid] = {
            "scene_id": sid,
            "name": kv.get("name") or name or sid,
            "seed": kv.get("seed") or kv.get("seed_id"),
            "structure": kv.get("结构", ""),
            "materials": kv.get("材质", ""),
            "landmarks": kv.get("标志物", ""),
            "palette": kv.get("配色", ""),
            "lighting": kv.get("光照", ""),
            "prompt_fragment": kv.get("Prompt fragment", ""),
        }
    return result


def parse_script_md(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    text = read_text(path)
    scenes: List[Dict[str, Any]] = []
    matches = list(re.finditer(r"(?m)^##\s+(S\d+)(?:\s*[—\-–]\s*(.*?))?\s*$", text))
    for idx, match in enumerate(matches):
        scene_id = match.group(1).strip()
        title = (match.group(2) or "").strip()
        body = text[match.end():matches[idx + 1].start() if idx + 1 < len(matches) else len(text)]
        scene: Dict[str, Any] = {
            "scene_id": scene_id,
            "location": title,
            "duration_sec": 0,
            "summary": "",
            "emotion_beat": "",
            "narration": "",
            "dialogue": [],
            "shot_plan": [],
        }
        speaker: Optional[str] = None
        for line in body.splitlines():
            stripped = line.strip()
            match = re.match(r"^- (duration_sec|location|character_style_override|summary|emotion_beat|narration|no_vo):\s*(.*)$", stripped)
            if match:
                key, value = match.group(1), match.group(2).strip()
                value = clean_value(value)
                if key == "duration_sec":
                    try:
                        scene["duration_sec"] = int(float(value))
                    except ValueError:
                        scene["duration_sec"] = 0
                elif key == "location":
                    scene["location"] = value or scene.get("location", "")
                else:
                    scene[key] = value
                continue
            if stripped.startswith("- shot_id:"):
                shot: Dict[str, Any] = {"shot_id": stripped.split(":", 1)[1].strip()}
                scene.setdefault("shot_plan", []).append(shot)
                speaker = None
                continue
            if scene.get("shot_plan"):
                shot_match = re.match(r"^\s{2,}([a-zA-Z_]+):\s*(.*)$", stripped)
                if shot_match:
                    key, value = shot_match.group(1), shot_match.group(2).strip()
                    current_shot = scene["shot_plan"][-1]
                    if key == "duration_sec":
                        try:
                            current_shot[key] = int(float(value))
                        except ValueError:
                            current_shot[key] = 0
                    elif key == "sfx":
                        current_shot[key] = re.findall(r"[^\[\],，\s]+", value)
                    else:
                        current_shot[key] = value
                    continue
            if stripped.startswith("- speaker:"):
                speaker = clean_value(stripped.split(":", 1)[1])
                scene.setdefault("dialogue", []).append({"speaker": speaker, "line": ""})
                continue
            if speaker is not None and scene.get("dialogue") and "line:" in stripped:
                scene["dialogue"][-1]["line"] = clean_value(stripped.split(":", 1)[1])
        scenes.append(scene)
    if not scenes:
        return None
    return {"scenes": scenes, "source_md": str(path)}


def load_script(project: Path, script_path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if script_path is not None:
        path = script_path
    else:
        path = None
        for rel in (
            "scripts/02_script.json",
            "scripts/02_script.md",
            "02_script.json",
            "02_script.md",
        ):
            candidate = project / rel
            if candidate.exists():
                path = candidate
                break
    if path is None or not path.exists():
        return None
    if path.suffix.lower() == ".json":
        data = load_json(path)
        if isinstance(data, dict) and isinstance(data.get("scenes"), list):
            script = data
        elif isinstance(data, list):
            script = {"scenes": data}
        else:
            return None
        script["source_json"] = str(path)
        return script
    return parse_script_md(path)


def extract_dialogue_characters(scenes: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    result: List[Tuple[str, str]] = []
    for scene in scenes:
        for line in scene.get("dialogue", []) or []:
            speaker = str(line.get("speaker", "")).strip()
            if not speaker:
                continue
            cid = slugify(speaker, f"char_{len(result) + 1}")
            result.append((cid, speaker))
    # Deduplicate by id.
    seen: Dict[str, str] = {}
    for cid, name in result:
        seen.setdefault(cid, name)
    return list(seen.items())


def split_list(value: str) -> List[str]:
    return [part.strip().rstrip("。.") for part in re.split(r"[、，,;/；\n]+", value or "") if part.strip()]


def appears_in_scene(scene: Dict[str, Any], character: Dict[str, Any]) -> bool:
    cid = str(character.get("character_id", ""))
    name = str(character.get("name", ""))
    summary = str(scene.get("summary", ""))
    location = str(scene.get("location", ""))
    if any(str(d.get("speaker", "")) in (name, cid) for d in scene.get("dialogue", []) or []):
        return True
    if cid and cid in summary:
        return True
    if name and (name in summary or name in location):
        return True
    if name and len(name) >= 2 and name[:2] in summary:
        return True
    return False


def emotion_profile(scene: Dict[str, Any]) -> Dict[str, Any]:
    beat = str(scene.get("emotion_beat", "")).strip().lower()
    if beat in EMOTION_PROFILES:
        return EMOTION_PROFILES[beat]
    text = " ".join([
        str(scene.get("summary", "")),
        str(scene.get("location", "")),
        str(scene.get("emotion_beat", "")),
    ]).lower()
    for key, profile in EMOTION_PROFILES.items():
        if key in text:
            return profile
    return DEFAULT_EMOTION_PROFILE


def has_any(text: str, keywords: Tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(keyword.lower() in lower for keyword in keywords)


def infer_environment(scene: Dict[str, Any], scene_bible: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    scene_id = str(scene.get("scene_id", "")).strip()
    bible = scene_bible or {}
    text = " ".join([
        str(scene.get("summary", "")),
        str(scene.get("location", "")),
        str(bible.get("name", "")),
        str(bible.get("structure", "")),
        str(bible.get("materials", "")),
        str(bible.get("lighting", "")),
        str(bible.get("palette", "")),
    ])
    has_wind = has_any(text, ("风", "wind", "吹动", "飘动", "呼啸", "凛冽", "breeze", "gust"))
    has_grass = has_any(text, ("草", "grass", "草原", "草地", "麦浪"))
    has_snow = has_any(text, ("雪", "snow", "飘雪", "风雪", "霜"))
    has_rain = has_any(text, ("雨", "rain", "湿", "积水", "雨夜"))
    has_leaf = has_any(text, ("叶", "落叶", "枫", "樱花", "花瓣", "竹叶"))
    has_dust = has_any(text, ("沙", "尘", "dust", "黄沙", "飞沙"))
    has_mist = has_any(text, ("雾", "mist", "云海", "山雾", "烟"))

    wind_level = "strong" if has_wind and any(k in text.lower() for k in ("呼啸", "凛冽", "强风", "gust", "狂风")) else ("moderate" if has_wind else "light")
    density = "heavy" if has_snow and any(k in text.lower() for k in ("大雪", "暴雪", "heavy")) else ("light" if has_snow else "none")
    rain_density = "heavy" if has_rain and any(k in text.lower() for k in ("暴雨", "大雨", "heavy")) else ("light" if has_rain else "none")
    direction = "screen-left to right" if int(re.sub(r"\D", "", scene_id) or 0) % 2 else "screen-right to left"

    particles: List[str] = []
    if has_snow:
        particles.append("snowflakes falling at a slight angle")
    if has_rain:
        particles.append("rain streaks with wet-surface reflections")
    if has_leaf:
        particles.append("falling leaves carried by wind")
    if has_dust:
        particles.append("dust blowing across the ground")
    if has_mist:
        particles.append("mist layers in the midground")
    if not particles and not has_rain and not has_snow:
        particles.append("subtle floating dust in light beams")

    atmosphere: List[str] = []
    if has_rain:
        atmosphere.append("wet reflections")
    if has_snow:
        atmosphere.append("cold breath")
    if has_wind:
        atmosphere.append("wind-swept cloth and hair")
    if has_grass:
        atmosphere.append("moving grass layers")
    if has_mist:
        atmosphere.append("layered mist")
    if bible and bible.get("lighting"):
        atmosphere.append(str(bible["lighting"]))
    if bible and bible.get("palette"):
        atmosphere.append(str(bible["palette"]))
    if not atmosphere:
        atmosphere.append("natural cinematic depth")

    return {
        "weather": "snowy" if has_snow else ("rainy" if has_rain else ("windy" if has_wind else "clear")),
        "wind": {"enabled": has_wind or has_grass or has_leaf or has_snow, "intensity": wind_level, "direction": direction},
        "grass": {
            "enabled": has_grass,
            "motion": "sweeping waves" if wind_level == "strong" else ("gentle sway" if has_grass else "still"),
            "intensity": 0.8 if wind_level == "strong" else (0.4 if has_grass else 0.0),
        },
        "snow": {"enabled": has_snow, "density": density, "fall_speed": 0.2 if density == "light" else 0.45},
        "rain": {"enabled": has_rain, "density": rain_density, "angle_deg": 18},
        "particles": particles,
        "atmosphere": atmosphere,
    }


def infer_music(scene: Dict[str, Any], environment: Dict[str, Any]) -> Dict[str, Any]:
    profile = emotion_profile(scene)
    duration = float(scene.get("duration_sec") or 0)
    intensity = profile.get("music", {}).get("intensity_curve", [])
    sfx: List[Dict[str, Any]] = []
    if scene.get("sfx"):
        for item in scene["sfx"]:
            if isinstance(item, str):
                sfx.append({"name": item, "enter_at_s": round(duration * 0.35, 2), "duration_s": 1.2})
            elif isinstance(item, dict):
                sfx.append(item)
    if not sfx:
        if environment["rain"]["enabled"]:
            sfx.append({"name": "rain", "enter_at_s": 0.0, "duration_s": round(duration, 2)})
        if environment["wind"]["enabled"]:
            sfx.append({"name": "wind", "enter_at_s": 0.0, "duration_s": round(duration, 2)})
        if environment["snow"]["enabled"]:
            sfx.append({"name": "soft snow movement", "enter_at_s": 0.0, "duration_s": round(duration, 2)})
    return {
        "bgm_mood": profile["music"]["bgm_mood"],
        "tempo_bpm": profile["music"]["tempo_bpm"],
        "instruments": profile["music"]["instruments"],
        "intensity_curve": intensity,
        "start_at_s": 0,
        "end_at_s": round(duration, 2),
        "sfx": sfx,
    }


def build_shot_plan(
    scene: Dict[str, Any],
    scene_index: int,
    characters: List[Dict[str, Any]],
    scene_bible: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    existing = scene.get("shot_plan") or []
    if existing:
        shots: List[Dict[str, Any]] = []
        for shot in existing:
            item = dict(shot)
            item.setdefault("shot_type", "medium")
            item.setdefault("camera_move", "static")
            item.setdefault("action_beat", scene.get("summary", ""))
            item.setdefault("lip_motion", "closed")
            item.setdefault("sfx", [])
            item.setdefault("image_prompt_hint", build_image_prompt_hint(scene, item, characters, scene_bible))
            item.setdefault("motion_prompt_hint", build_motion_prompt_hint(scene, item, None, scene_bible))
            if "music_cue" not in item:
                item["music_cue"] = {
                    "start_at_s": 0,
                    "end_at_s": int(item.get("duration_sec") or scene.get("duration_sec") or 0),
                }
            shots.append(item)
        return shots

    duration = int(scene.get("duration_sec") or 0)
    count = max(1, min(4, round(duration / 3) or 1))
    base = duration // count if count else 0
    remainder = duration - base * count
    shots = []
    cursor = 0.0
    for idx in range(count):
        shot_duration = base + (1 if idx < remainder else 0)
        shot: Dict[str, Any] = {
            "shot_id": f"S{scene_index + 1}.{idx + 1}",
            "duration_sec": shot_duration,
            "shot_type": SHOT_TYPE_CYCLE[(scene_index + idx) % len(SHOT_TYPE_CYCLE)],
            "camera_move": CAMERA_CYCLE[(scene_index + idx) % len(CAMERA_CYCLE)],
            "action_beat": scene.get("summary", ""),
            "sfx": [],
            "lip_motion": "speaking" if (scene.get("dialogue") or scene.get("narration")) and idx == count - 1 else "closed",
        }
        shot["image_prompt_hint"] = build_image_prompt_hint(scene, shot, characters, scene_bible)
        shot["motion_prompt_hint"] = build_motion_prompt_hint(scene, shot, cursor, scene_bible)
        shot["music_cue"] = {
            "start_at_s": round(cursor, 2),
            "end_at_s": round(cursor + shot_duration, 2),
        }
        shots.append(shot)
        cursor += shot_duration
    return shots


def build_image_prompt_hint(
    scene: Dict[str, Any],
    shot: Dict[str, Any],
    characters: List[Dict[str, Any]],
    scene_bible: Optional[Dict[str, Any]] = None,
) -> str:
    active = [c for c in characters if appears_in_scene(scene, c)] or characters
    names = "、".join(dict.fromkeys([c.get("name", c.get("character_id")) for c in active])) or "主要人物"
    env = infer_environment(scene, scene_bible)
    effects = [particle for particle in env["particles"] if particle]
    return (
        f"{shot.get('shot_type', 'medium')} shot of {names} at {scene.get('location', 'scene')}, "
        f"{scene.get('summary', '')}, {emotion_profile(scene)['lighting']}, "
        f"environment effects: {'; '.join(effects) or 'clean natural depth'}, "
        "Seedream layered prompt: format + subject + composition + lighting + style + lock clause"
    )


def build_motion_prompt_hint(
    scene: Dict[str, Any],
    shot: Dict[str, Any],
    start_time: Optional[float],
    scene_bible: Optional[Dict[str, Any]] = None,
) -> str:
    duration = int(shot.get("duration_sec") or scene.get("duration_sec") or 4)
    start = start_time if start_time is not None else 0
    env = infer_environment(scene, scene_bible)
    dynamics = []
    if env["wind"]["enabled"]:
        dynamics.append(f"wind {env['wind']['intensity']} from {env['wind']['direction']}")
    if env["grass"]["enabled"]:
        dynamics.append(f"grass {env['grass']['motion']}")
    if env["snow"]["enabled"]:
        dynamics.append(f"snow density {env['snow']['density']}")
    if env["rain"]["enabled"]:
        dynamics.append(f"rain density {env['rain']['density']}")
    return (
        f"{shot.get('action_beat', scene.get('summary', 'continuous action'))}, "
        f"camera {shot.get('camera_move', 'static')} from {start}s to {start + duration}s, "
        f"{'; '.join(dynamics) or 'no forced particles'}, "
        f"mouth {'open for speech' if shot.get('lip_motion') == 'speaking' else 'closed'}, "
        "no foot sliding, no floating, physical gravity and inertia"
    )


def infer_transition(prev: Optional[Dict[str, Any]], curr: Dict[str, Any], curr_index: int) -> str:
    if prev is None:
        return "fade-in"
    prev_beat = str(prev.get("emotion_beat", "")).lower()
    curr_beat = str(curr.get("emotion_beat", "")).lower()
    prev_loc = str(prev.get("location", ""))
    curr_loc = str(curr.get("location", ""))
    text = " ".join([str(curr.get("summary", "")), str(curr.get("emotion_beat", ""))]).lower()
    if prev_loc == curr_loc and prev_beat == curr_beat:
        return "cut"
    if any(key in text for key in ("突然", "闪过", "闪回", "回忆", "cut to")):
        return "match-cut"
    if curr_beat in ("tense", "fearful", "angry") or prev_beat in ("tense", "fearful", "angry"):
        return "whip-pan" if curr_index % 2 else "crash-zoom"
    if curr_beat in ("tender", "warm", "soft", "hopeful") or prev_beat in ("tender", "warm", "soft", "hopeful"):
        return "dissolve"
    if int(curr.get("duration_sec") or 0) > 8:
        return "fade"
    return "cut"


def build_characters(scenes: List[Dict[str, Any]], bible: Dict[str, Dict[str, Any]], analysis: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    order: List[str] = []
    data: Dict[str, Dict[str, Any]] = {}

    for cid, item in bible.items():
        data[cid] = {
            "character_id": cid,
            "name": item.get("name") or cid,
            "role": item.get("role", "supporting"),
            "seed": item.get("seed"),
            "voice_id": item.get("voice_id"),
            "appearance": item.get("appearance", {}),
            "prompt_fragment": item.get("prompt_fragment", ""),
        }
        order.append(cid)

    for cid, item in analysis.items():
        entry = data.setdefault(cid, {
            "character_id": cid,
            "name": item.get("name") or cid,
            "role": "supporting",
            "appearance": {},
            "prompt_fragment": "",
        })
        entry["name"] = entry.get("name") or item.get("name") or cid
        entry["episode_goal"] = item.get("episode_goal", "")
        entry["emotional_arc"] = item.get("emotional_arc", "")
        entry["actions"] = item.get("actions", "")
        entry["voice_tone"] = item.get("voice_tone", "")
        entry["continuity_notes"] = item.get("continuity_notes", "")
        if cid not in order:
            order.append(cid)

    for cid, name in extract_dialogue_characters(scenes):
        if cid not in data:
            data[cid] = {"character_id": cid, "name": name, "role": "supporting", "appearance": {}, "prompt_fragment": ""}
            order.append(cid)

    result: List[Dict[str, Any]] = []
    for cid in order:
        item = data[cid]
        profile = DEFAULT_EMOTION_PROFILE
        for scene in scenes:
            if appears_in_scene(scene, item):
                profile = emotion_profile(scene)
                break
        traits = list(profile.get("personality", DEFAULT_EMOTION_PROFILE["personality"]))
        actions_text = " ".join(split_list(str(item.get("actions", ""))))
        action_traits = []
        for keywords, trait in (
            (("警惕", "躲闪", "缩在", "害怕", "防御"), "敏感防御"),
            (("试探", "靠近", "接近", "观察"), "试探性接近"),
            (("信任", "依赖", "蹭", "依偎"), "愿意建立信任"),
            (("保护", "照顾", "抱起", "背", "承担"), "责任感强"),
            (("战斗", "挥剑", "斩", "格挡", "追击"), "行动果断"),
        ):
            if has_any(actions_text, keywords):
                action_traits.append(trait)
        traits.extend(action_traits)
        role = item.get("role", "supporting")
        if role == "protagonist":
            traits.append("主动推动剧情")
        elif role == "antagonist":
            traits.append("制造冲突")
        else:
            traits.append("提供情感或信息支持")
        actions = split_list(str(item.get("actions", "")))
        behavior = []
        for action in actions:
            behavior.append(action)
        if not behavior:
            for keywords, label in BEHAVIOR_KEYWORDS:
                if has_any(" ".join([str(item.get("name", "")), " ".join(str(s.get("summary", "")) for s in scenes)]), keywords):
                    behavior.append(label)
                    break
        if not behavior:
            behavior.append("根据场景动作自动推进")
        item["personality"] = list(dict.fromkeys(traits))
        item["behavior_patterns"] = behavior
        item["motivation"] = item.get("episode_goal", "从剧本行动和场景目标推断")
        item["action_beats"] = actions or behavior
        if not item.get("voice_tone"):
            item["voice_tone"] = "待 Step 6 锁定语音 ID"
        result.append(item)
    return result


def _resolve(project: Path, *candidates: str) -> Optional[Path]:
    """Return the first existing path under project, walking up to the series root."""
    current: Optional[Path] = project
    for _ in range(6):
        if current is None:
            break
        for rel in candidates:
            path = current / rel
            if path.exists():
                return path
        current = current.parent
    return None


def _load_meta(project: Path) -> Dict[str, Any]:
    """Load manifest.json (helper) or 00_meta.json (main skill) and normalize keys."""
    raw = load_json(project / "manifest.json") or load_json(project / "00_meta.json") or {}
    if not isinstance(raw, dict):
        return {}
    return {
        "project_slug": raw.get("project_slug") or raw.get("slug") or project.name,
        "target_length_sec": raw.get("target_length_sec") or raw.get("target_length"),
        "character_style": raw.get("character_style") or raw.get("style"),
        "motion_mode": raw.get("motion_mode"),
    }


def build_analysis(project: Path, script: Dict[str, Any]) -> Dict[str, Any]:
    meta = _load_meta(project)
    scenes = script.get("scenes", [])
    bible_path = _resolve(project, "character-bible.md", "scripts/character-bible.md")
    analysis_path = _resolve(project, "scripts/02_character_analysis.md", "02_character_analysis.md")
    scene_bible_path = _resolve(project, "scene-bible.md", "scripts/scene-bible.md")
    bible = parse_character_bible(bible_path) if bible_path is not None else {}
    analysis = parse_character_analysis(analysis_path) if analysis_path is not None else {}
    scene_bibles = parse_scene_bible(scene_bible_path) if scene_bible_path is not None else {}
    characters = build_characters(scenes, bible, analysis)

    analyzed_scenes: List[Dict[str, Any]] = []
    transitions: List[Dict[str, str]] = []
    prev_scene: Optional[Dict[str, Any]] = None
    for index, raw_scene in enumerate(scenes):
        scene = dict(raw_scene)
        scene.setdefault("scene_id", f"S{index + 1}")
        scene.setdefault("location", "")
        scene.setdefault("duration_sec", 0)
        scene.setdefault("summary", "")
        scene.setdefault("emotion_beat", "")
        scene.setdefault("dialogue", [])
        scene.setdefault("narration", "")
        scene_id = str(scene["scene_id"])
        scene_bible = scene_bibles.get(scene_id) or scene_bibles.get(str(scene.get("scene_ref", ""))) or {}
        if not scene_bible:
            location = str(scene.get("location", ""))
            scene_bible = next(
                (item for item in scene_bibles.values() if item.get("name") and (item["name"] in location or location in item["name"])),
                {},
            )
        profile = emotion_profile(scene)
        environment = infer_environment(scene, scene_bible)
        music = infer_music(scene, environment)
        shot_plan = build_shot_plan(scene, index, characters, scene_bible)
        if prev_scene is None:
            transition_in = "fade-in"
        else:
            transition_in = infer_transition(prev_scene, scene, index)
        transitions.append({
            "from": prev_scene["scene_id"] if prev_scene else "open",
            "to": scene_id,
            "transition": transition_in,
            "reason": "emotion/location continuity rule",
        })
        analyzed_scenes.append({
            "scene_id": scene_id,
            "location": scene.get("location", ""),
            "duration_sec": scene.get("duration_sec", 0),
            "summary": scene.get("summary", ""),
            "emotion_beat": scene.get("emotion_beat", ""),
            "mood": profile["mood"],
            "lighting": profile["lighting"],
            "music": music,
            "environment": environment,
            "transition_in": transition_in,
            "transition_out": "cut",
            "dialogue": scene.get("dialogue", []),
            "narration": scene.get("narration", ""),
            "shot_plan": shot_plan,
            "scene_bible_notes": {
                "structure": scene_bible.get("structure", ""),
                "materials": scene_bible.get("materials", ""),
                "landmarks": scene_bible.get("landmarks", ""),
                "palette": scene_bible.get("palette", ""),
                "lighting": scene_bible.get("lighting", ""),
                "prompt_fragment": scene_bible.get("prompt_fragment", ""),
            },
        })
        prev_scene = analyzed_scenes[-1]

    for index, scene in enumerate(analyzed_scenes):
        scene["transition_out"] = transitions[index + 1]["transition"] if index + 1 < len(transitions) else "cut"

    continuity_notes: List[str] = []
    for cid, item in bible.items():
        if item.get("seed"):
            continuity_notes.append(f"{cid} locked seed {item['seed']}; canonical refs must be reused")
    for sid, item in scene_bibles.items():
        if item.get("scene_id"):
            continuity_notes.append(f"{sid} locked scene prompt_fragment must stay unchanged")
    if not continuity_notes:
        continuity_notes.append("Step 0 bible refs and seeds must be loaded before image generation")

    return {
        "analysis_version": 1,
        "project_slug": meta.get("project_slug") or project.name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target_length_sec": meta.get("target_length_sec"),
        "character_style": meta.get("character_style"),
        "motion_mode": meta.get("motion_mode"),
        "characters": characters,
        "scenes": analyzed_scenes,
        "transitions": transitions,
        "continuity_notes": continuity_notes,
        "deai_notes": [
            "非说话镜头嘴巴闭合",
            "动作必须符合重力、惯性和脚步不滑",
            "风吹、草动、飘雪等粒子必须与镜头运动和音乐节奏对齐",
            "每个角色和场景在 Step 5 必须引用 canonical refs，禁止从文字重造",
        ],
    }


def render_markdown(analysis: Dict[str, Any]) -> str:
    lines = [
        f"# Script Deep Analysis — {analysis.get('project_slug')}",
        "",
        f"- generated_at: {analysis.get('generated_at')}",
        f"- target_length_sec: {analysis.get('target_length_sec')}",
        f"- character_style: {analysis.get('character_style')}",
        f"- motion_mode: {analysis.get('motion_mode')}",
        "",
        "## Characters",
        "",
    ]
    for char in analysis.get("characters", []):
        lines.append(f"### {char.get('character_id')} — {char.get('name')}")
        lines.append("")
        lines.append(f"- role: {char.get('role')}")
        lines.append(f"- personality: {'、'.join(char.get('personality', []))}")
        lines.append(f"- motivation: {char.get('motivation')}")
        lines.append(f"- behavior_patterns: {'、'.join(char.get('behavior_patterns', []))}")
        lines.append(f"- voice_tone: {char.get('voice_tone')}")
        appearance = char.get("appearance") or {}
        if isinstance(appearance, dict):
            lines.append(f"- appearance: 脸型 {appearance.get('face', 'pending')} / 发型 {appearance.get('hair', 'pending')} / 体型 {appearance.get('body', 'pending')} / 服装 {appearance.get('costume', 'pending')} / 道具 {appearance.get('props', 'pending')}")
        if char.get("emotional_arc"):
            lines.append(f"- emotional_arc: {char.get('emotional_arc')}")
        if char.get("action_beats"):
            lines.append(f"- action_beats: {'、'.join(char.get('action_beats', []))}")
        lines.append("")

    lines.append("## Scenes")
    lines.append("")
    for scene in analysis.get("scenes", []):
        lines.append(f"### {scene.get('scene_id')} — {scene.get('location')}")
        lines.append("")
        lines.append(f"- duration_sec: {scene.get('duration_sec')}")
        lines.append(f"- summary: {scene.get('summary')}")
        lines.append(f"- emotion_beat: {scene.get('emotion_beat')}")
        lines.append(f"- mood: {scene.get('mood')}")
        lines.append(f"- lighting: {scene.get('lighting')}")
        music = scene.get("music", {})
        lines.append(f"- music: {music.get('bgm_mood')} / {music.get('tempo_bpm')} BPM / {'、'.join(music.get('instruments', []))}")
        lines.append(f"- music_curve: {json.dumps(music.get('intensity_curve', []), ensure_ascii=False)}")
        sfx = music.get("sfx", [])
        if sfx:
            sfx_text = "、".join(f"{item.get('name')} @ {item.get('enter_at_s')}s" for item in sfx)
            lines.append(f"- sfx: {sfx_text}")
        env = scene.get("environment", {})
        lines.append(f"- weather: {env.get('weather')}")
        wind = env.get("wind", {})
        lines.append(f"- wind: {wind.get('intensity')} / {wind.get('direction')}")
        grass = env.get("grass", {})
        lines.append(f"- grass: {'enabled' if grass.get('enabled') else 'disabled'} / {grass.get('motion')} / {grass.get('intensity')}")
        snow = env.get("snow", {})
        lines.append(f"- snow: {'enabled' if snow.get('enabled') else 'disabled'} / {snow.get('density')} / fall_speed {snow.get('fall_speed')}")
        rain = env.get("rain", {})
        lines.append(f"- rain: {'enabled' if rain.get('enabled') else 'disabled'} / {rain.get('density')} / angle {rain.get('angle_deg')}")
        lines.append(f"- particles: {'、'.join(env.get('particles', []))}")
        lines.append(f"- atmosphere: {'、'.join(env.get('atmosphere', []))}")
        lines.append(f"- transition_in: {scene.get('transition_in')}")
        lines.append(f"- transition_out: {scene.get('transition_out')}")
        lines.append("")
        lines.append("#### Shot plan")
        lines.append("")
        for shot in scene.get("shot_plan", []):
            lines.append(f"- {shot.get('shot_id')} | {shot.get('shot_type')} | {shot.get('camera_move')} | {shot.get('duration_sec')}s | lip={shot.get('lip_motion')}")
            if shot.get("image_prompt_hint"):
                lines.append(f"  - image_prompt_hint: {shot.get('image_prompt_hint')}")
            if shot.get("motion_prompt_hint"):
                lines.append(f"  - motion_prompt_hint: {shot.get('motion_prompt_hint')}")
            if shot.get("music_cue"):
                lines.append(f"  - music_cue: {json.dumps(shot.get('music_cue'), ensure_ascii=False)}")
        lines.append("")

    lines.append("## Transitions")
    lines.append("")
    for transition in analysis.get("transitions", []):
        lines.append(f"- {transition.get('from')} -> {transition.get('to')}: {transition.get('transition')} ({transition.get('reason')})")
    lines.append("")
    lines.append("## Continuity & De-AI notes")
    lines.append("")
    for note in analysis.get("continuity_notes", []):
        lines.append(f"- {note}")
    for note in analysis.get("deai_notes", []):
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Automated deep analysis for the approved script.")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--script", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    project = args.project_dir
    if not project.is_dir():
        print(f"project directory not found: {project}")
        return 1
    script = load_script(project, args.script)
    if script is None:
        print("script not found; create 02_script.json or 02_script.md first")
        return 1
    analysis = build_analysis(project, script)
    scripts_dir = project / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    output_json = args.output_json or scripts_dir / "03_deep_analysis.json"
    output_md = args.output_md or scripts_dir / "03_deep_analysis.md"
    if args.dry_run:
        print(json.dumps(analysis, ensure_ascii=False, indent=2))
        return 0
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(render_markdown(analysis), encoding="utf-8")
    print(f"wrote: {output_json}")
    print(f"wrote: {output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
