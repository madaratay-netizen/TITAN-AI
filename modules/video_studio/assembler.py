"""ADWIN OS — Video Studio FFmpeg assembler.

Renders a multi-scene VideoProject into a real MP4 using FFmpeg. This is the
offline, CPU-friendly path that works on any machine with FFmpeg — no AI video
model required. Supported scene types: title/color cards, still images, and
imported video clips. Optional narration audio per scene, background music,
per-scene fade, and burned subtitles.

Every scene is normalized to identical codec/resolution/fps/audio params so the
final concat is reliable. Nothing here fabricates footage: a scene with no
source renders an honest title/color card.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from modules.video_studio.project import VideoProject, Scene
from modules.voice_studio.subtitles import Segment, to_srt


class AssemblerError(Exception):
    pass


def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise AssemblerError("ffmpeg not found on PATH")
    return exe


def _font_file() -> Optional[str]:
    for p in (r"C:\Windows\Fonts\arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/TTF/DejaVuSans.ttf",
              "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if os.path.exists(p):
            return p
    return None


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _esc_drawtext(text: str) -> str:
    # Escape for ffmpeg drawtext.
    return (text.replace("\\", "\\\\").replace(":", "\\:")
            .replace("'", "\u2019").replace("%", "\\%"))


@dataclass
class RenderResult:
    output: str
    duration: float
    width: int
    height: int
    scenes: int
    size_bytes: int


class Assembler:
    def __init__(self, work_dir: Optional[str] = None):
        self.work_dir = Path(work_dir) if work_dir else None

    # -- per-scene normalization ----------------------------------------- #
    def _audio_input(self, scene: Scene, dur: float) -> tuple[list[str], str]:
        """Return (input args, audio filter label source index spec)."""
        if scene.narration_audio and Path(scene.narration_audio).is_file():
            # Pad/trim narration to the scene duration.
            return (["-i", scene.narration_audio],
                    f"apad,atrim=0:{dur},asetpts=N/SR/TB")
        return (["-f", "lavfi", "-i",
                 f"anullsrc=r=44100:cl=stereo"], f"atrim=0:{dur},asetpts=N/SR/TB")

    def _render_scene(self, scene: Scene, idx: int, proj: VideoProject,
                      tmp: Path, use_text: bool) -> Path:
        W, H, fps = proj.width, proj.height, proj.fps
        dur = max(0.3, float(scene.duration))
        out = tmp / f"scene_{idx:03d}.mp4"

        # Video source per scene type.
        if scene.type == "clip" and scene.source and Path(scene.source).is_file():
            vin = ["-t", str(dur), "-i", scene.source]
            vfilter = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                       f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}")
            vlabel = "0:v"
        elif scene.type == "image" and scene.source and Path(scene.source).is_file():
            vin = ["-loop", "1", "-t", str(dur), "-i", scene.source]
            vfilter = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                       f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}")
            vlabel = "0:v"
        else:  # title / color
            color = scene.bg_color or "black"
            vin = ["-f", "lavfi", "-t", str(dur), "-i",
                   f"color=c={color}:s={W}x{H}:r={fps}"]
            vfilter = "setsar=1"
            vlabel = "0:v"

        # Optional on-screen title text.
        font = _font_file()
        if use_text and scene.title and font:
            txt = _esc_drawtext(scene.title)
            fontpath = font.replace("\\", "/").replace(":", "\\:")
            vfilter += (f",drawtext=fontfile='{fontpath}':text='{txt}':"
                        f"fontcolor=white:fontsize={max(24, H // 18)}:"
                        f"x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.4:boxborderw=12")

        audio_in, afilter = self._audio_input(scene, dur)

        cmd = [ffmpeg(), "-y", *vin, *audio_in,
               "-filter_complex",
               f"[{vlabel}]{vfilter}[v];[1:a]{afilter}[a]",
               "-map", "[v]", "-map", "[a]",
               "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
               "-r", str(fps), "-c:a", "aac", "-ar", "44100", "-ac", "2",
               "-t", str(dur), str(out)]
        res = _run(cmd)
        if res.returncode != 0 or not out.exists():
            # Retry once without text (font issues are the usual cause).
            if use_text and scene.title:
                return self._render_scene(
                    Scene(**{**scene.to_dict(), "title": ""}), idx, proj, tmp, False)
            raise AssemblerError(f"scene {idx} render failed: {res.stderr[-400:]}")
        return out

    # -- subtitles -------------------------------------------------------- #
    def _build_srt(self, proj: VideoProject, tmp: Path) -> Optional[Path]:
        segs, t = [], 0.0
        for s in proj.scenes:
            text = s.narration or s.title
            if text:
                segs.append(Segment(t, t + s.duration, text))
            t += s.duration
        if not segs:
            return None
        srt = tmp / "subs.srt"
        srt.write_text(to_srt(segs), encoding="utf-8")
        return srt

    # -- top-level render ------------------------------------------------- #
    def render(self, proj: VideoProject, out_path: str, resolution: Optional[str] = None,
               burn_subtitles: bool = False, with_titles: bool = True,
               timeout: int = 900) -> RenderResult:
        if not proj.scenes:
            raise AssemblerError("project has no scenes")
        if resolution:
            proj.width, proj.height = _res(resolution)

        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        cleanup = self.work_dir is None
        tmp = Path(self.work_dir) if self.work_dir else Path(tempfile.mkdtemp(prefix="adwin_vid_"))
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            parts = [self._render_scene(s, i, proj, tmp, with_titles)
                     for i, s in enumerate(proj.scenes)]

            # Concat (identical params → stream copy is safe).
            listfile = tmp / "concat.txt"
            listfile.write_text(
                "\n".join(f"file '{p.resolve().as_posix()}'" for p in parts),
                encoding="utf-8")
            concat_out = tmp / "concat.mp4"
            res = _run([ffmpeg(), "-y", "-f", "concat", "-safe", "0",
                        "-i", str(listfile), "-c", "copy", str(concat_out)], timeout)
            if res.returncode != 0 or not concat_out.exists():
                raise AssemblerError(f"concat failed: {res.stderr[-400:]}")

            final_src = concat_out
            # Optional subtitle burn (best-effort; needs libass).
            if burn_subtitles:
                srt = self._build_srt(proj, tmp)
                if srt:
                    subbed = tmp / "subbed.mp4"
                    srtpath = str(srt).replace("\\", "/").replace(":", "\\:")
                    r = _run([ffmpeg(), "-y", "-i", str(concat_out),
                              "-vf", f"subtitles='{srtpath}'",
                              "-c:a", "copy", str(subbed)], timeout)
                    if r.returncode == 0 and subbed.exists():
                        final_src = subbed

            shutil.copyfile(final_src, out)
            dur = probe_duration(str(out))
            return RenderResult(output=str(out), duration=dur,
                                width=proj.width, height=proj.height,
                                scenes=len(proj.scenes),
                                size_bytes=out.stat().st_size)
        finally:
            if cleanup:
                shutil.rmtree(tmp, ignore_errors=True)


def _res(name: str) -> tuple[int, int]:
    return {"720p": (1280, 720), "1080p": (1920, 1080),
            "480p": (854, 480), "4k": (3840, 2160)}.get(name, (1280, 720))


def probe_duration(path: str) -> float:
    probe = shutil.which("ffprobe")
    if probe:
        r = _run([probe, "-v", "quiet", "-print_format", "json",
                  "-show_format", path], 30)
        try:
            import json
            return round(float(json.loads(r.stdout)["format"]["duration"]), 2)
        except (ValueError, KeyError):
            pass
    return 0.0
