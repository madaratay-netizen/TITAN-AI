"""ADWIN OS — Developer Lab coding assistant.

Code generation / explanation / review / debugging via a local LLM. Prefers a
dedicated coding model (e.g. qwen2.5-coder) when installed, otherwise uses the
default general model. All inference is local; the assistant NEVER executes
anything — it only produces text. Running code goes through executor.py's
approval gate.
"""
from __future__ import annotations

from modules.chat import ollama_client

CODING_MODEL_HINTS = ("coder", "code", "deepseek", "qwen2.5-coder")

GEN_SYSTEM = (
    "You are ADWIN Developer Lab, a local coding assistant. Produce correct, "
    "idiomatic code. Return the code in a single fenced block with the right "
    "language tag, then a brief explanation. Never claim to have run the code."
)
REVIEW_SYSTEM = (
    "You are a senior code reviewer. Point out real bugs, security issues, and "
    "clear improvements, most important first. Be concrete and concise."
)
EXPLAIN_SYSTEM = (
    "You explain code clearly and accurately for a developer. Be concise."
)
DEBUG_SYSTEM = (
    "You are a debugging assistant. Given code and an error, identify the most "
    "likely cause and the minimal fix. Show the corrected snippet."
)


def pick_coding_model(installed: list[str], default: str) -> str:
    """Prefer an installed coding-specialized model, else the default."""
    for name in installed:
        low = name.lower()
        if any(h in low for h in CODING_MODEL_HINTS):
            return name
    return default


class CodingAssistant:
    def __init__(self, host: str = "http://127.0.0.1:11434",
                 default_model: str = "qwen3.5:4b"):
        self.host = host
        self.default_model = default_model

    def _model(self, override: str | None = None) -> str:
        if override:
            return override
        st = ollama_client.status(self.host)
        return pick_coding_model(st.models, self.default_model)

    def generate(self, task: str, language: str = "python",
                 model: str | None = None) -> dict:
        prompt = f"Write {language} code for this task:\n\n{task}"
        text = ollama_client.chat(prompt, model=self._model(model), host=self.host,
                                  system=GEN_SYSTEM, think=False)
        return {"result": text, "model": self._model(model)}

    def explain(self, code: str, model: str | None = None) -> dict:
        text = ollama_client.chat(f"Explain this code:\n\n{code}",
                                  model=self._model(model), host=self.host,
                                  system=EXPLAIN_SYSTEM, think=False)
        return {"result": text, "model": self._model(model)}

    def review(self, code: str, model: str | None = None) -> dict:
        text = ollama_client.chat(f"Review this code:\n\n{code}",
                                  model=self._model(model), host=self.host,
                                  system=REVIEW_SYSTEM, think=False)
        return {"result": text, "model": self._model(model)}

    def debug(self, code: str, error: str, model: str | None = None) -> dict:
        prompt = f"Code:\n\n{code}\n\nError / symptom:\n{error}"
        text = ollama_client.chat(prompt, model=self._model(model), host=self.host,
                                  system=DEBUG_SYSTEM, think=False)
        return {"result": text, "model": self._model(model)}
