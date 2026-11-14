"""Video Studio tests — project/scene model + a real FFmpeg render.

The render test runs only if ffmpeg is present (skipped, not faked, otherwise).
"""
import shutil

import pytest

from modules.video_studio.project import VideoProject, Scene, new_scene
from modules.video_studio import generation
from modules.video_studio.assembler import Assembler, probe_duration
from core.hardware_detection.detector import (
    HardwareReport, MemoryInfo, GPUInfo, Accel)


# -- project / scene model -------------------------------------------------- #
def test_new_project_and_scene():
    p = VideoProject.new("demo")
    s = p.add_scene(new_scene(type="title", title="Hi", duration=3))
    assert p.scenes and p.get(s.id) is s
    assert p.total_duration() == 3.0


def test_reorder_and_duration_and_remove():
    p = VideoProject.new("demo")
    a = p.add_scene(new_scene(id="a", duration=2))
    b = p.add_scene(new_scene(id="b", duration=4))
    assert [s.id for s in p.scenes] == ["a", "b"]
    p.reorder("b", 0)
    assert [s.id for s in p.scenes] == ["b", "a"]
    assert p.set_duration("a", 5) and p.get("a").duration == 5
    assert p.total_duration() == 9.0
    assert p.remove_scene("a") and len(p.scenes) == 1


def test_persistence_roundtrip(tmp_path):
    p = VideoProject.new("demo", 1920, 1080, 25)
    p.add_scene(new_scene(type="color", title="S1", duration=2))
    path = p.save(tmp_path / "proj.json")
    loaded = VideoProject.load(path)
    assert loaded.name == "demo" and loaded.width == 1920
    assert loaded.scenes[0].title == "S1"


def test_three_minute_is_multi_scene():
    # A 3-minute video is many scenes, never one request.
    p = VideoProject.new("long")
    for i in range(45):
        p.add_scene(new_scene(duration=4))
    assert p.total_duration() == 180.0 and len(p.scenes) == 45


# -- AI generation gate (honest) -------------------------------------------- #
def _machine(vram_mb, vendor="nvidia"):
    gpus = [GPUInfo(vendor=vendor, model="GPU", vram_total_mb=vram_mb,
                    vram_free_mb=vram_mb)] if vram_mb else []
    return HardwareReport(memory=MemoryInfo(16, 11), gpus=gpus, accel=Accel())


def test_ai_video_unavailable_on_small_gpu():
    cap = generation.capability(_machine(4096))
    assert cap.available is False and "VRAM" in cap.reason


def test_generate_clip_raises_when_unsupported():
    with pytest.raises(generation.VideoGenUnavailable):
        generation.generate_clip(_machine(4096), "a sunset", 4.0)


# -- real render (skipped without ffmpeg) ----------------------------------- #
def test_render_real_mp4(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    p = VideoProject.new("render", 640, 360, 24)
    p.add_scene(new_scene(type="title", title="One", bg_color="navy", duration=1.5))
    p.add_scene(new_scene(type="color", title="Two", bg_color="teal", duration=1.0))
    out = tmp_path / "out.mp4"
    r = Assembler().render(p, str(out), with_titles=True)
    assert out.exists() and r.size_bytes > 0
    assert 2.0 <= r.duration <= 3.5        # ~2.5s total, allow encoder slack
    assert r.scenes == 2
