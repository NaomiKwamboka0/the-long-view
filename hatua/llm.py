"""Optional rewrite with a LOCAL open-weights model (Ollama on the same machine).

Off by default. Hatua never calls an outside service. Turn it on with
    HATUA_LLM=ollama  HATUA_MODEL=qwen2.5:7b
and Ollama running on localhost. If the model is missing, slow, or drops a citation,
Hatua keeps the template draft, which is always complete and cited.
"""
from __future__ import annotations

import json
import os
import urllib.request

from .local_model import local_host, open_local

PROMPT = """Rewrite the teacher draft below in plain, warm, simple English for a busy Kenyan
junior school teacher. Keep every line that starts with '-' as a separate line starting
with '-'. Keep every citation in square brackets exactly as written. Do not add facts,
labels, pathway or career suggestions, or comparisons with other learners.

DRAFT:
{draft}
"""


def enabled() -> bool:
    return os.environ.get("HATUA_LLM", "").lower() == "ollama"


def model_name() -> str:
    return "ollama:" + os.environ.get("HATUA_MODEL", "qwen2.5:7b")


def rewrite_is_sound(original: str, rewritten: str) -> bool:
    """A rewrite may reword, but it may not add a line or move a citation to another line.

    Line-for-line comparison is deliberate: it is the only check that survives rewording,
    and it stops a model from attaching an existing citation to a new claim.
    """
    from . import guard  # imported here so llm.py stays cheap to load

    before, after = original.splitlines(), rewritten.splitlines()
    if len(before) != len(after):
        return False
    return all(set(guard.citations(old)) == set(guard.citations(new))
               for old, new in zip(before, after))


def polish(text: str, language: str = "en") -> str | None:
    if not enabled() or language != "en":
        return None
    host = local_host()
    if not host:
        return None  # local only, by design
    body = json.dumps({"model": model_name().split(":", 1)[1], "prompt": PROMPT.format(draft=text),
                       "stream": False, "options": {"temperature": 0}}).encode()
    try:
        req = urllib.request.Request(f"{host}/api/generate", data=body,
                                     headers={"Content-Type": "application/json"})
        with open_local(req, timeout=120) as resp:
            return json.loads(resp.read())["response"].strip()
    except Exception:
        return None
