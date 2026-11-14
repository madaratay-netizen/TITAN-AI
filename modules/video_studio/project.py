"""TITAN AI — Video Studio project & scene model.

A video is a *multi-scene production*, persisted as JSON so work survives
interruption (resume-after-crash). Edit operations: add, remove, reorder,
adjust duration, regenerate a scene's description. A 3-minute video is just a
project with enough scenes — never a single generation request.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Literal

SceneType = Literal["clip", "image", "title", "color"]
TRANSITIONS = {"cut", "fade"}


@dataclass
class Scene:
    id: str
    type: SceneType = "title"
    duration: float = 4.0
    source: str = ""             # file path for clip/image
    title: str = ""              # text for title cards / overlay
    description: str = ""        # scene/prompt description (for storyboard/AI)
    narration: str = ""          # narration text (→ TTS)
    narration_audio: str = ""    # path to a generated/imported narration wav
    bg_color: str = "black"
    transition: str = "cut"      # transition INTO this scene

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VideoProject:
    id: str
    name: str
    width: int = 1280
    height: int = 720
    fps: int = 30
    bg_music: str = ""           # optional background-music path
    created_at: float = field(default_factory=time.time)
    scenes: list[Scene] = field(default_factory=list)

    # -- lifecycle -------------------------------------------------------- #
    @classmethod
    def new(cls, name: str, width: int = 1280, height: int = 720, fps: int = 30) -> "VideoProject":
        return cls(id=uuid.uuid4().hex[:12], name=name, width=width, height=height, fps=fps)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "width": self.width,
                "height": self.height, "fps": self.fps, "bg_music": self.bg_music,
                "created_at": self.created_at,
                "scenes": [s.to_dict() for s in self.scenes],
                "total_duration": self.total_duration()}

    @classmethod
    def from_dict(cls, d: dict) -> "VideoProject":
        p = cls(id=d["id"], name=d["name"], width=d.get("width", 1280),
                height=d.get("height", 720), fps=d.get("fps", 30),
                bg_music=d.get("bg_music", ""), created_at=d.get("created_at", time.time()))
        p.scenes = [Scene(**s) for s in d.get("scenes", [])]
        return p

    def save(self, path: str | Path) -> str:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return str(path)

    @classmethod
    def load(cls, path: str | Path) -> "VideoProject":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    # -- scene edits ------------------------------------------------------ #
    def total_duration(self) -> float:
        return round(sum(max(0.1, s.duration) for s in self.scenes), 2)

    def add_scene(self, scene: Scene, index: Optional[int] = None) -> Scene:
        if index is None:
            self.scenes.append(scene)
        else:
            self.scenes.insert(max(0, min(index, len(self.scenes))), scene)
        return scene

    def remove_scene(self, scene_id: str) -> bool:
        before = len(self.scenes)
        self.scenes = [s for s in self.scenes if s.id != scene_id]
        return len(self.scenes) < before

    def get(self, scene_id: str) -> Optional[Scene]:
        return next((s for s in self.scenes if s.id == scene_id), None)

    def reorder(self, scene_id: str, new_index: int) -> bool:
        s = self.get(scene_id)
        if not s:
            return False
        self.scenes.remove(s)
        self.scenes.insert(max(0, min(new_index, len(self.scenes))), s)
        return True

    def set_duration(self, scene_id: str, duration: float) -> bool:
        s = self.get(scene_id)
        if not s or duration <= 0:
            return False
        s.duration = round(float(duration), 2)
        return True


def new_scene(**kwargs) -> Scene:
    kwargs.setdefault("id", uuid.uuid4().hex[:8])
    return Scene(**kwargs)
