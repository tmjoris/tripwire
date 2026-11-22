"""LLM judges from different model families, all asked the same thing: does this SQL answer the question?

Each judge runs through a tool already on the machine (the claude and copilot CLIs, a local ollama server, or the
Gemini API) and returns a Verdict. None of them sees the ground-truth label.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPT = """You are grading an answer to a text-to-SQL question.

Question: {question}
Hint: {evidence}

Database schema (SQLite):
{schema}

Candidate SQL:
```sql
{sql}
```

Does the candidate SQL correctly answer the question on this database?
Reply with JSON only: {{"verdict": "correct" or "incorrect", "reason": "<one sentence>"}}"""


@dataclass
class Verdict:
    correct: bool | None   # None when the reply could not be read as a verdict
    reason: str
    seconds: float
    cost_usd: float | None
    model: str
    raw: str


@lru_cache(maxsize=64)
def schema(db_path: str, max_chars: int = 12_000) -> str:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        ddl = [r[0] for r in conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND sql IS NOT NULL")]
    finally:
        conn.close()
    text = "\n".join(ddl)
    return text if len(text) <= max_chars else text[:max_chars] + "\n-- (schema truncated)"


def build_prompt(question: str, evidence: str, db_path: Path, sql: str, template: str = PROMPT) -> str:
    return template.format(question=question, evidence=evidence or "(none)", schema=schema(str(db_path)), sql=sql)


_VERDICT = re.compile(r"\{[^{}]*\"verdict\"[^{}]*\}", re.S)


def parse_verdict(text: str) -> tuple[bool | None, str]:
    """Read {"verdict": ..., "reason": ...} out of a reply that may have other text around it."""
    for m in _VERDICT.finditer(text or ""):
        try:
            d = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        v = str(d.get("verdict", "")).strip().lower()
        if v in ("correct", "incorrect"):
            return v == "correct", str(d.get("reason", ""))
    return None, ""


class Judge:
    name = "judge"

    def ask(self, prompt: str) -> tuple[str, float | None, str]:
        """Send the prompt; return (reply text, cost in USD or None, model that answered)."""
        raise NotImplementedError

    def grade(self, prompt: str) -> Verdict:
        start = time.monotonic()
        try:
            text, cost, model = self.ask(prompt)
        except Exception as e:  # noqa: BLE001 - one failed call must not stop a run; it is recorded instead
            return Verdict(None, f"error: {e}", time.monotonic() - start, None, self.name, "")
        correct, reason = parse_verdict(text)
        return Verdict(correct, reason, time.monotonic() - start, cost, model, text[-2000:])


class ClaudeJudge(Judge):
    def __init__(self, model: str = "haiku"):
        self.model, self.name = model, f"claude-{model}"

    def ask(self, prompt):
        p = subprocess.run(["claude", "-p", "--model", self.model, "--tools", "", "--strict-mcp-config",
                            "--output-format", "json"], input=prompt, capture_output=True, text=True, timeout=180)
        d = json.loads(p.stdout)
        if d.get("is_error"):
            raise RuntimeError(str(d.get("result"))[:200])
        return d.get("result", ""), d.get("total_cost_usd"), ",".join(d.get("modelUsage") or [self.model])


class CopilotJudge(Judge):
    """Copilot picks the model itself on this plan ("auto"); the model it chose is recorded per call."""
    name = "copilot-auto"

    def ask(self, prompt):
        with tempfile.TemporaryDirectory() as empty:     # no tools and an empty folder: it can only answer
            p = subprocess.run(["copilot", "-p", prompt, "--model", "auto", "--available-tools", "", "--no-ask-user"],
                               capture_output=True, text=True, timeout=240, cwd=empty)
        out = p.stdout + p.stderr
        m = re.search(r"selected (.+?) because", out)
        return out, None, (m.group(1).strip() if m else "auto")


class OllamaJudge(Judge):
    def __init__(self, model: str = "qwen2.5-coder:7b", url: str = "http://127.0.0.1:11434"):
        self.model, self.url = model, url
        self.name = f"ollama-{model.replace(':', '-')}"    # ':' is not allowed in artifact file names

    def ask(self, prompt):
        body = {"model": self.model, "prompt": prompt, "stream": False, "format": "json",
                "options": {"temperature": 0, "num_ctx": 4096}}
        req = urllib.request.Request(f"{self.url}/api/generate", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        d = json.load(urllib.request.urlopen(req, timeout=1800))
        return d.get("response", ""), 0.0, self.model


class GeminiJudge(Judge):
    def __init__(self, model: str = "gemini-2.5-flash"):
        self.model, self.name = model, model

    def ask(self, prompt):
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("set GEMINI_API_KEY")
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key})
        try:
            d = json.load(urllib.request.urlopen(req, timeout=120))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.read()[:150]!r}") from None
        return d["candidates"][0]["content"]["parts"][0]["text"], None, self.model


JUDGES = {"claude": ClaudeJudge, "copilot": CopilotJudge, "ollama": OllamaJudge, "gemini": GeminiJudge}
