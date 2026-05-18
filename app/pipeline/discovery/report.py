from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import DiscoveredMessageType, MessageTypeAssignment


def get_discovery_report(db: Session):
    total_types = db.query(func.count(DiscoveredMessageType.id)).scalar() or 0
    total_assignments = db.query(func.count(MessageTypeAssignment.id)).scalar() or 0

    top_types = (
        db.query(
            DiscoveredMessageType.id,
            DiscoveredMessageType.sender_key,
            DiscoveredMessageType.example_count,
            DiscoveredMessageType.review_status,
            DiscoveredMessageType.manually_labeled_template_id,
        )
        .order_by(DiscoveredMessageType.example_count.desc())
        .limit(20)
        .all()
    )

    return {
        "total_discovered_types": total_types,
        "total_assignments": total_assignments,
        "top_types": [
            {
                "id": str(row.id),
                "sender_key": row.sender_key,
                "example_count": row.example_count,
                "review_status": row.review_status,
                "manually_labeled_template_id": row.manually_labeled_template_id,
            }
            for row in top_types
        ],
    }
def get_discovered_types_with_examples(db: Session, limit: int = 20):
    rows = (
        db.query(DiscoveredMessageType)
        .order_by(DiscoveredMessageType.example_count.desc())
        .limit(limit)
        .all()
    )

    result = []
    for row in rows:
        rep_msg = row.representative_normalized_message
        result.append({
            "id": str(row.id),
            "sender_key": row.sender_key,
            "example_count": row.example_count,
            "review_status": row.review_status,
            "manually_labeled_template_id": row.manually_labeled_template_id,
            "signature_text": row.signature_text[:1000],
            "representative_normalized_message_id": str(row.representative_normalized_message_id) if row.representative_normalized_message_id else None,
            "representative_preview": rep_msg.normalized_text[:1000] if rep_msg else None,
        })

    return result