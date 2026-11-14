"""TITAN AI — Code Animation Renderer.

Renders a DETERMINISTIC code animation (HTML/Canvas/SVG) to MP4 by capturing
frames with a headless browser, then assembling with FFmpeg. Fully offline, no
GPU, no AI model. This is the engineering-explainer technique (precise,
reproducible 2.5D visuals) — the opposite of AI image generation.

Animation contract — the HTML page must define:
    window.TITAN_DURATION  : number   (seconds)
    window.seekTo(t)       : function (render the exact frame at time t seconds)
    window.TITAN_FPS       : number   (optional; default 30)

Because every frame is a pure function of `t`, the output is reproducible and
exact — ideal for engineering diagrams, production lines, and labelled parts.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class AnimationError(Exception):
    pass


@dataclass
class AnimationResult:
    output: str
    frames: int
    duration_s: float
    width: int
    height: int
    size_bytes: int


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise AnimationError("ffmpeg not found on PATH")
    return exe


def render_html_animation(html_path: str, out_path: str, width: int = 1280,
                          height: int = 720, fps: int = 30,
                          narration_audio: Optional[str] = None,
                          load_timeout_ms: int = 30000) -> AnimationResult:
    """Render an HTML animation (seekTo contract) to an MP4. Offline, no GPU."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise AnimationError(
            "Playwright not installed. Run: pip install playwright && "
            "python -m playwright install chromium") from exc

    html = Path(html_path).resolve()
    if not html.is_file():
        raise AnimationError(f"HTML not found: {html_path}")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    frames_dir = Path(tempfile.mkdtemp(prefix="titan_anim_"))

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-gpu"])
            page = browser.new_page(viewport={"width": width, "height": height},
                                    device_scale_factor=1)
            page.goto(html.as_uri())
            # Wait for the animation contract to be ready.
            page.wait_for_function(
                "typeof window.seekTo==='function' && "
                "typeof window.TITAN_DURATION==='number'", timeout=load_timeout_ms)
            duration = float(page.evaluate("window.TITAN_DURATION"))
            use_fps = int(page.evaluate("window.TITAN_FPS || 0") or fps)
            total = max(1, int(round(duration * use_fps)))
            for f in range(total):
                page.evaluate("(t) => window.seekTo(t)", f / use_fps)
                page.screenshot(path=str(frames_dir / f"frame_{f:05d}.png"))
            browser.close()

        # Assemble frames -> MP4 (+ optional narration).
        cmd = [_ffmpeg(), "-y", "-framerate", str(use_fps),
               "-i", str(frames_dir / "frame_%05d.png")]
        if narration_audio and Path(narration_audio).is_file():
            cmd += ["-i", str(narration_audio), "-c:a", "aac", "-shortest"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(use_fps), str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if r.returncode != 0 or not out.exists():
            raise AnimationError(f"ffmpeg failed: {r.stderr[-400:]}")

        return AnimationResult(output=str(out), frames=total, duration_s=round(duration, 2),
                               width=width, height=height, size_bytes=out.stat().st_size)
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)
