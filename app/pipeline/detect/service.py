# app/pipeline/detect/service.py

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import NormalizedMessage
from app.models import TemplateMatch
from app.pipeline.detect.detector import detect_template
from app.pipeline.detect.utils import serialize_rule_matches


def detect_pending_templates(db: Session, limit: int | None = None) -> dict:
    """
    Detect templates for normalized messages that do not yet have a template match.
    Returns a summary dict.
    """

    query = (
        db.query(NormalizedMessage)
        .outerjoin(
            TemplateMatch,
            TemplateMatch.normalized_message_id == NormalizedMessage.id
        )
        .filter(TemplateMatch.id.is_(None))
        .order_by(NormalizedMessage.normalized_at.asc())
    )

    if limit is not None:
        query = query.limit(limit)

    pending_messages = query.all()

    processed = 0
    matched = 0
    unknown = 0
    ambiguous = 0

    for msg in pending_messages:
        result = detect_template(msg.normalized_text)

        db_row = TemplateMatch(
            normalized_message_id=msg.id,
            template_id=result.template_id,
            confidence=result.confidence,
            status=result.status,
            matched_rules_json=serialize_rule_matches(result.matched_rules),
            detector_version=result.detector_version,
        )
        db.add(db_row)

        processed += 1
        if result.status == "matched":
            matched += 1
        elif result.status == "unknown":
            unknown += 1
        elif result.status == "ambiguous":
            ambiguous += 1

    db.commit()

    return {
        "processed": processed,
        "matched": matched,
        "unknown": unknown,
        "ambiguous": ambiguous,
    }

def redetect_all_templates(db: Session, limit: int | None = None) -> dict:
    query = db.query(NormalizedMessage).order_by(NormalizedMessage.normalized_at.asc())

    if limit is not None:
        query = query.limit(limit)

    messages = query.all()

    processed = 0
    matched = 0
    unknown = 0
    ambiguous = 0

    for msg in messages:
        result = detect_template(msg.normalized_text)

        existing = (
            db.query(TemplateMatch)
            .filter(TemplateMatch.normalized_message_id == msg.id)
            .first()
        )

        if existing:
            existing.template_id = result.template_id
            existing.confidence = result.confidence
            existing.status = result.status
            existing.matched_rules_json = serialize_rule_matches(result.matched_rules)
            existing.detector_version = result.detector_version
        else:
            db.add(
                TemplateMatch(
                    normalized_message_id=msg.id,
                    template_id=result.template_id,
                    confidence=result.confidence,
                    status=result.status,
                    matched_rules_json=serialize_rule_matches(result.matched_rules),
                    detector_version=result.detector_version,
                )
            )

        processed += 1
        if result.status == "matched":
            matched += 1
        elif result.status == "unknown":
            unknown += 1
        elif result.status == "ambiguous":
            ambiguous += 1

    db.commit()

    return {
        "processed": processed,
        "matched": matched,
        "unknown": unknown,
        "ambiguous": ambiguous,
    }