"""Secret redaction for anything that leaves the server (logs, chat, JSON)."""
import os
import re

_PATTERNS = [re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), re.compile(r"sk-[A-Za-z0-9]{20,}")]
_SECRET_ENV_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


def redact(text: str) -> str:
    if not text:
        return text
    for name, value in os.environ.items():
        if value and len(value) >= 8 and any(h in name.upper() for h in _SECRET_ENV_HINTS):
            text = text.replace(value, "[REDACTED]")
    for pat in _PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text
