"""TITAN AI — Scene Builder (component-composition pipeline, offline).

Open-ended engineering videos WITHOUT pre-made whole-scene templates: the local
LLM only produces a small JSON "scene spec" (which components, where, labels,
connections, timing). The heavy visual quality lives in scene_lib/framework.html
(a reusable component library). This makes the task easy enough for a small
local model, yet open-ended by composition.

Pipeline:  Arabic request --(LLM planner)--> scene JSON --(validate/repair)-->
           framework.html + spec --(headless render)--> MP4
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Optional

from modules.chat import ollama_client
from modules.video_studio.code_animation import render_html_animation, AnimationResult

FRAMEWORK = Path(__file__).with_name("scene_lib") / "framework.html"
COMPONENT_TYPES = [
    # water / general
    "pump", "tank", "valve", "gauge", "filter", "motor",
    # production line
    "conveyor", "mixer", "compressor", "fan",
    # electrical
    "panel", "transformer", "generator",
    # sewage / people / generic
    "manhole", "person", "box",
]

PLANNER_SYSTEM = (
    "You plan an engineering explainer animation. Output ONLY a JSON object, no "
    "prose. Canvas is 1280x720.\n"
    "Component types ONLY (pick what matches the system):\n"
    "  water/general: pump, tank, valve, gauge, filter, motor\n"
    "  production:     conveyor, mixer, compressor, fan\n"
    "  electrical:     panel, transformer, generator\n"
    "  sewage/people:  manhole, person, box\n"
    "Schema:\n"
    '{\n'
    '  "title":"<Arabic>", "subtitle":"<English>", "duration":<7-14>,\n'
    '  "components":[{"id":"a","type":"pump","x":640,"y":380,'
    '"label":"<Arabic>","en":"<English>","appear":1.0}],\n'
    '  "pipes":[{"from":"a","to":"b","appear":2.0,"label":"<optional Arabic>"}],\n'
    '  "camera":[{"t":0,"zoom":1,"x":640,"y":360},'
    '{"t":5,"zoom":1.8,"x":<focus x>,"y":<focus y>},'
    '{"t":7,"zoom":1,"x":640,"y":360}]\n'
    "}\n"
    "Rules: spread components (x 150-1130, y 200-540); sequential appear times; "
    "pipes connect component ids (or an [x,y] point); Arabic labels. OPTIONAL "
    "camera keyframes do a focus/zoom shot onto one component then zoom back "
    "(zoom 1-2.2). Pick components that match the requested system."
)

_EXAMPLE = (
    '{"title":"محطة ضخ حريق","subtitle":"Fire Pump Station","duration":9,'
    '"components":[{"id":"t","type":"tank","x":220,"y":380,"label":"خزان المياه","en":"water tank","appear":0.5},'
    '{"id":"p","type":"pump","x":620,"y":400,"label":"مضخة الحريق","en":"fire pump","appear":1.5},'
    '{"id":"m","type":"motor","x":620,"y":250,"label":"الموتور","en":"motor","appear":2.2},'
    '{"id":"g","type":"gauge","x":860,"y":300,"label":"مقياس الضغط","en":"pressure gauge","appear":3.0}],'
    '"pipes":[{"from":"t","to":"p","appear":2.6,"label":"خط السحب"},'
    '{"from":"p","to":[1080,400],"appear":3.4,"label":"خط الطرد"}]}'
)


def _clamp(v, lo, hi, default):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def plan_scene(request: str, model: str, host: str = "http://127.0.0.1:11434") -> dict:
    """Ask the local LLM for a scene spec. Returns raw parsed dict (unvalidated)."""
    prompt = (f"Request (Arabic): {request}\n\nExample of the exact JSON format:\n"
              f"{_EXAMPLE}\n\nNow output ONLY the JSON for the request above.")
    raw = ollama_client.chat(prompt, model=model, host=host,
                             system=PLANNER_SYSTEM, think=False,
                             options={"temperature": 0.4, "num_predict": 900})
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("planner did not return JSON")
    return json.loads(m.group(0))


def validate_repair(spec: dict) -> dict:
    """Make the spec safe to render: valid types, clamped coords, valid refs."""
    out = {"title": str(spec.get("title", "مشهد هندسي"))[:60],
           "subtitle": str(spec.get("subtitle", "TITAN AI"))[:80],
           "duration": _clamp(spec.get("duration", 9), 5, 20, 9),
           "components": [], "pipes": []}
    ids = set()
    for i, c in enumerate(spec.get("components", [])[:12]):
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or f"c{i}")
        if cid in ids:
            cid = f"{cid}_{i}"
        ids.add(cid)
        ctype = str(c.get("type", "box")).lower()
        if ctype not in COMPONENT_TYPES:
            ctype = "box"
        out["components"].append({
            "id": cid, "type": ctype,
            "x": _clamp(c.get("x", 200 + i * 160), 120, 1160, 300),
            "y": _clamp(c.get("y", 380), 170, 580, 380),
            "label": str(c.get("label", ""))[:40],
            "en": str(c.get("en", ""))[:40],
            "appear": _clamp(c.get("appear", 0.5 + i), 0, 18, 0.5 + i)})
    for p in spec.get("pipes", [])[:12]:
        if not isinstance(p, dict):
            continue
        frm, to = p.get("from"), p.get("to")
        if frm not in ids:
            continue
        if not (to in ids or (isinstance(to, list) and len(to) == 2)):
            continue
        out["pipes"].append({"from": frm, "to": to,
                             "appear": _clamp(p.get("appear", 2), 0, 18, 2),
                             "label": str(p.get("label", ""))[:30]})
    cam = spec.get("camera")
    if isinstance(cam, list) and cam:
        kfs = []
        for k in cam[:8]:
            if not isinstance(k, dict):
                continue
            kfs.append({"t": _clamp(k.get("t", 0), 0, out["duration"], 0),
                        "zoom": _clamp(k.get("zoom", 1), 0.8, 2.6, 1),
                        "x": _clamp(k.get("x", 640), 0, 1280, 640),
                        "y": _clamp(k.get("y", 360), 0, 720, 360)})
        if kfs:
            kfs.sort(key=lambda k: k["t"])
            out["camera"] = kfs
    if not out["components"]:
        raise ValueError("no valid components produced")
    return out


def build_html(spec: dict) -> str:
    """Inject the scene spec into the framework template."""
    tpl = FRAMEWORK.read_text(encoding="utf-8")
    return tpl.replace("__TITAN_SCENE_JSON__", json.dumps(spec, ensure_ascii=False))


def make_video(request: str, out_path: str, model: str,
               host: str = "http://127.0.0.1:11434",
               width: int = 1280, height: int = 720, fps: int = 30) -> dict:
    """Full pipeline: Arabic request -> validated scene -> MP4. Offline, no GPU."""
    raw = plan_scene(request, model=model, host=host)
    spec = validate_repair(raw)
    html = build_html(spec)
    tmp = Path(tempfile.mkdtemp(prefix="titan_scene_")) / "scene.html"
    tmp.write_text(html, encoding="utf-8")
    result: AnimationResult = render_html_animation(
        str(tmp), out_path, width=width, height=height, fps=fps)
    return {"spec": spec, "output": result.output, "frames": result.frames,
            "duration_s": result.duration_s,
            "components": [c["type"] for c in spec["components"]]}
