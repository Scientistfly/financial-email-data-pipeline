import re
import html
import hashlib


def build_sender_key(from_email: str | None, subject: str | None = None) -> str:
    """
    Very simple sender grouping key.
    For now, use the sender email lowercased.
    Later you can improve this to institution-level grouping.
    """
    sender = (from_email or "").strip().lower()
    return sender or "unknown"


def build_signature_text(normalized_text: str) -> str:
    text = html.unescape(normalized_text or "")
    text = text.lower()

    # normalize whitespace early
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # datetime first, then date/time
    text = re.sub(
        r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\s+a\s+las\s+\d{1,2}:\d{2}\b",
        "[DATETIME]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b", "[DATE]", text)
    text = re.sub(r"\b\d{1,2}:\d{2}\b", "[TIME]", text)

    # money
    text = re.sub(r"\$\s?\d+(?:[.,]\d{2})?", "[AMOUNT]", text)
    text = re.sub(r"\b\d+[.,]\d{2}\b", "[AMOUNT]", text)

    # emails
    text = re.sub(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", "[EMAIL]", text)

    # masked cards/accounts like 10XXXX26 or 455179XXXXXXX692
    text = re.sub(r"\b[\dxX\*]{6,}\b", "[MASKED_NUMBER]", text)

    # long references
    text = re.sub(r"\b\d{5,}\b", "[REFERENCE]", text)

    # collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def build_signature_hash(signature_text: str) -> str:
    return hashlib.sha256(signature_text.encode("utf-8")).hexdigest()