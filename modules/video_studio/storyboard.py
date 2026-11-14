"""TITAN AI — Video Studio storyboard generator.

Turns a project idea into a scene breakdown using the LOCAL LLM (Ollama). This
is the script / scene-description step of the production workflow. It produces a
structured list of scenes; the actual footage is produced later (imported clips,
title cards, or — optionally and when supported — AI-generated clips).

Honesty: this generates a PLAN (storyboard), never actual video. The caller must
not present a storyboard as a rendered video.
"""
from __future__ import annotations

import json
import re

from modules.chat import ollama_client
from modules.video_studio.project import VideoProject, new_scene

STORYBOARD_SYSTEM = (
    "You are a video director. Given an idea, output a concise scene-by-scene "
    "breakdown as STRICT JSON: a list of objects with keys "
    '"title" (short), "description" (visual description), "narration" (one '
    'spoken sentence), and "duration" (seconds, 3-8). Output ONLY the JSON array.'
)


def _extract_json_array(text: str):
    # Pull the first [...] block out of the model output.
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise ValueError("model did not return a JSON array")
    return json.loads(m.group(0))


def generate_storyboard(idea: str, model: str, scene_count: int = 5,
                        host: str = "http://127.0.0.1:11434") -> list[dict]:
    """Ask the local LLM for a scene breakdown. Returns a list of scene dicts."""
    prompt = (f"Idea: {idea}\n\nProduce about {scene_count} scenes as a JSON array. "
              f"Keep narration short and factual.")
    raw = ollama_client.chat(prompt, model=model, host=host,
                             system=STORYBOARD_SYSTEM, think=False,
                             options={"temperature": 0.7})
    data = _extract_json_array(raw)
    scenes = []
    for item in data:
        if not isinstance(item, dict):
            continue
        dur = item.get("duration", 4)
        try:
            dur = max(2.0, min(12.0, float(dur)))
        except (TypeError, ValueError):
            dur = 4.0
        scenes.append({
            "title": str(item.get("title", ""))[:120],
            "description": str(item.get("description", ""))[:500],
            "narration": str(item.get("narration", ""))[:300],
            "duration": dur,
        })
    if not scenes:
        raise ValueError("no scenes parsed from model output")
    return scenes


def project_from_storyboard(name: str, scenes: list[dict],
                            width: int = 1280, height: int = 720) -> VideoProject:
    """Build a VideoProject of title-card scenes from a storyboard."""
    proj = VideoProject.new(name, width=width, height=height)
    for s in scenes:
        proj.add_scene(new_scene(
            type="title", title=s.get("title", ""),
            description=s.get("description", ""),
            narration=s.get("narration", ""),
            duration=float(s.get("duration", 4.0))))
    return proj
