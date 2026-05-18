# app/pipeline/ingest/gmail_ingest.py
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Optional, Tuple, Dict, List

from googleapiclient.discovery import Resource
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select

from app.models import RawMessage, User
from app.gmail.gmail_client import build_gmail_service

PROVIDER = "gmail"


def build_test_query(after_date: Optional[str] = None) -> str:
    """
    Bank-only query (temporary).
    Gmail query format uses YYYY/MM/DD for after/before.
    We will ingest from Jan 1 of current year: after:YYYY/01/01
    """
    base = (
        "("
        "from:notificaciones@pacificard.com.ec OR "
        "from:intermail@bancopacifico.ec OR "
        "from:notificaciones@infopacificard.com.ec OR "
        "from:estadodecuenta@pacificard.com.ec"
        ")"
    )
    if after_date:
        return f"{base} after:{after_date}"
    return base


def _get_header(headers: list[dict[str, str]], name: str) -> Optional[str]:
    name_l = name.lower()
    for h in headers or []:
        if (h.get("name") or "").lower() == name_l:
            return h.get("value")
    return None


def _decode_body_data(data: Optional[str]) -> Optional[str]:
    if not data:
        return None
    try:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    except Exception:
        return None


def _extract_bodies(payload: dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    Return (body_text, body_html) decoded strings when available.
    Prefers collecting both if present.
    """
    body_text = None
    body_html = None

    def walk(p: dict[str, Any]):
        nonlocal body_text, body_html
        mime = p.get("mimeType")
        data = p.get("body", {}).get("data")

        if mime == "text/plain" and data and body_text is None:
            body_text = _decode_body_data(data)
        elif mime == "text/html" and data and body_html is None:
            body_html = _decode_body_data(data)

        for part in p.get("parts") or []:
            walk(part)

    walk(payload or {})
    return body_text, body_html


def _jan_1_after_date_yyyy_mm_dd_slash(now_utc: Optional[datetime] = None) -> str:
    """
    Gmail uses YYYY/MM/DD in search queries.
    "after:" is exclusive-ish; using Jan 1 is fine for our use.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    return f"{now_utc.year}/01/01"


def ingest_gmail_for_user(
    db: Session,
    user: User,
    query: str,
    max_results: int = 500,
) -> dict[str, int]:
    """
    Stage 0 for a single user: Gmail -> RawMessage (idempotent).
    No parsing. No classification. No transactions.
    """
    service: Resource = build_gmail_service(db, str(user.id))

    total_seen = 0
    total_inserted = 0

    page_token = None
    remaining = max_results

    while remaining > 0:
        batch_size = min(remaining, 100)
        resp = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=batch_size, pageToken=page_token)
            .execute()
        )

        msgs = resp.get("messages", [])
        if not msgs:
            break

        for m in msgs:
            total_seen += 1
            msg_id = m["id"]

            full_msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )

            payload = full_msg.get("payload") or {}
            headers = payload.get("headers") or []

            subject = _get_header(headers, "Subject")
            from_email = _get_header(headers, "From")
            to_email = _get_header(headers, "To")

            received_at = None
            internal_ms = full_msg.get("internalDate")
            if internal_ms:
                try:
                    received_at = datetime.fromtimestamp(int(internal_ms) / 1000.0, tz=timezone.utc)
                except Exception:
                    received_at = None

            body_text, body_html = _extract_bodies(payload)

            row = {
                "household_id": user.household_id,
                "user_id": user.id,
                "provider": PROVIDER,
                "source_message_id": msg_id,
                "thread_id": full_msg.get("threadId"),
                "from_email": from_email,
                "to_email": to_email,
                "subject": subject,
                "received_at": received_at,
                "snippet": full_msg.get("snippet"),
                "body_html": body_html,
                "body_text": body_text,
                "headers_json": headers,
                "raw_json": full_msg,  # optional but very useful
            }

            stmt = (
                insert(RawMessage)
                .values(**row)
                .on_conflict_do_nothing(index_elements=["provider", "user_id", "source_message_id"])
            )
            res = db.execute(stmt)
            if getattr(res, "rowcount", 0) == 1:
                total_inserted += 1

        db.commit()

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

        remaining -= len(msgs)

    return {"seen": total_seen, "inserted": total_inserted}


def ingest_gmail_for_household(
    db: Session,
    household_id: str,
    max_results_per_user: int = 500,
) -> dict[str, Any]:
    """
    Stage 0 for all users in a household.
    Uses build_test_query() for bank-only ingestion (temporary).
    Ingests from Jan 1 of current year.
    """
    after_date = _jan_1_after_date_yyyy_mm_dd_slash()
    query = build_test_query(after_date=after_date)

    users: List[User] = (
        db.execute(select(User).where(User.household_id == household_id))
        .scalars()
        .all()
    )

    totals = {"users": len(users), "seen": 0, "inserted": 0}
    per_user: Dict[str, dict[str, int]] = {}

    for u in users:
        # In Case a user has no OAUTH, but i think every user should or must have OAUTH
        try:
            stats = ingest_gmail_for_user(
                db=db,
                user=u,
                query=query,
                max_results=max_results_per_user,
            )
        except Exception as e:
            per_user[str(u.id)] = {"seen": 0, "inserted": 0, "error": str(e)}
            totals["errors"] = totals.get("errors", 0) + 1
            continue

        per_user[str(u.id)] = stats
        totals["seen"] += stats["seen"]
        totals["inserted"] += stats["inserted"]

    return {"query": query, "totals": totals, "per_user": per_user}