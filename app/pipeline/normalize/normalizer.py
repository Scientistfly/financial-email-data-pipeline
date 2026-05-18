# app/pipeline/normalize/normalizer.py
from __future__ import annotations

import hashlib
import html
import re
from typing import Optional, Tuple
from bs4 import BeautifulSoup

NORMALIZER_VERSION = "v1"


def html_to_text(body_html: str) -> str:
    soup = BeautifulSoup(body_html or "", "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n")


def normalize_text(text: str) -> str:
    text = html.unescape(text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_normalized(body_text: Optional[str], body_html: Optional[str]) -> Tuple[str, str]:
    base = body_text if (body_text and len(body_text.strip()) > 20) else html_to_text(body_html or "")
    normalized = normalize_text(base)
    h = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return normalized, h