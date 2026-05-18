# app/pipeline/normalize/normalize_job.py
from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.sql import exists

from app.models import RawMessage, NormalizedMessage
from app.pipeline.normalize.normalizer import build_normalized, NORMALIZER_VERSION


def normalize_pending_for_household(
    db: Session,
    household_id: str,
    limit: int = 1000,
) -> dict[str, int]:
    """
    Stage 1: raw_messages -> normalized_messages for a household.
    Creates one normalized row per raw message if missing.
    """
    # Efficient "missing normalized" query
    subq = select(NormalizedMessage.raw_message_id)
    rows = (
        db.execute(
            select(RawMessage)
            .where(RawMessage.household_id == household_id)
            .where(~RawMessage.id.in_(subq))
            .order_by(RawMessage.ingested_at.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    created = 0
    for rm in rows:
        normalized_text, normalized_hash = build_normalized(rm.body_text, rm.body_html)
        nm = NormalizedMessage(
            raw_message_id=rm.id,
            normalizer_version=NORMALIZER_VERSION,
            normalized_text=normalized_text,
            normalized_hash=normalized_hash,
        )
        db.add(nm)
        created += 1

    db.commit()
    return {"created": created}