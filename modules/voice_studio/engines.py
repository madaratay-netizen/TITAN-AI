"""ADWIN OS — Voice Studio engine detection.

Honestly reports which local voice engines are available on this machine so the
UI never claims a capability that isn't installed. Nothing here fabricates STT
or TTS output.

STT candidates : whisper.cpp binary (whisper-cli / main / whisper), faster-whisper (py)
TTS candidates : Piper binary, pyttsx3 (system SAPI/eSpeak/NSSpeech)
Audio          : ffmpeg (required for export/conversion)
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field

# Only unambiguous whisper.cpp binary names. Deliberately NOT "whisper" (that is
# openai-whisper's CLI, a different tool) or "main" (far too generic — it matches
# e.g. Windows' main.CPL). Over-loose names caused a false "STT available".
WHISPER_CPP_BINS = ("whisper-cli", "whisper-cpp")
PIPER_BINS = ("piper", "piper-tts")


def _which_any(names) -> str | None:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def _has_module(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


@dataclass
class VoiceCapabilities:
    whisper_cpp: str | None = None       # path if found
    faster_whisper: bool = False
    piper: str | None = None
    pyttsx3: bool = False
    ffmpeg: str | None = None
    tts_voices: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def stt_available(self) -> bool:
        return bool(self.whisper_cpp) or self.faster_whisper

    @property
    def tts_available(self) -> bool:
        return bool(self.piper) or self.pyttsx3

    def to_dict(self) -> dict:
        return {
            "stt": {
                "available": self.stt_available,
                "whisper_cpp": self.whisper_cpp,
                "faster_whisper": self.faster_whisper,
            },
            "tts": {
                "available": self.tts_available,
                "piper": self.piper,
                "pyttsx3": self.pyttsx3,
                "voices": self.tts_voices,
            },
            "ffmpeg": self.ffmpeg,
            "notes": self.notes,
        }


def _list_pyttsx3_voices() -> list[dict]:
    """Enumerate system voices, flagging Arabic availability honestly."""
    try:
        import pyttsx3  # type: ignore
        eng = pyttsx3.init()
        voices = []
        for v in eng.getProperty("voices"):
            langs = []
            for l in (getattr(v, "languages", []) or []):
                try:
                    langs.append(l.decode() if isinstance(l, bytes) else str(l))
                except Exception:
                    pass
            name = getattr(v, "name", "") or ""
            blob = (name + " " + getattr(v, "id", "") + " " + " ".join(langs)).lower()
            voices.append({
                "id": getattr(v, "id", ""),
                "name": name,
                "languages": langs,
                "arabic": ("ar" in [x.lower()[:2] for x in langs]) or "arab" in blob,
            })
        try:
            eng.stop()
        except Exception:
            pass
        return voices
    except Exception:
        return []


def detect() -> VoiceCapabilities:
    caps = VoiceCapabilities()
    caps.whisper_cpp = _which_any(WHISPER_CPP_BINS)
    caps.faster_whisper = _has_module("faster_whisper")
    caps.piper = _which_any(PIPER_BINS)
    caps.pyttsx3 = _has_module("pyttsx3")
    caps.ffmpeg = shutil.which("ffmpeg")

    if caps.pyttsx3:
        caps.tts_voices = _list_pyttsx3_voices()
    if not caps.stt_available:
        caps.notes.append(
            "No speech-to-text engine installed. Install whisper.cpp "
            "(whisper-cli on PATH) or `pip install faster-whisper`.")
        if shutil.which("whisper"):
            caps.notes.append(
                "Note: an external 'whisper' CLI is on PATH but it is not "
                "whisper.cpp and lives outside ADWIN's environment, so it is not "
                "used automatically.")
    if not caps.tts_available:
        caps.notes.append(
            "No text-to-speech engine installed. Install Piper, or `pip install pyttsx3`.")
    if not caps.ffmpeg:
        caps.notes.append("ffmpeg not found — audio export/conversion disabled.")
    if caps.tts_voices and not any(v["arabic"] for v in caps.tts_voices):
        caps.notes.append(
            "No Arabic system voice detected. Arabic TTS needs an Arabic voice "
            "(a Piper ar_* model, or a Windows Arabic language pack).")
    return caps
