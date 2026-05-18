# app/pipeline/detect/report.py

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import TemplateMatch


def get_template_detection_report(db: Session) -> dict:
    total = db.query(func.count(TemplateMatch.id)).scalar() or 0

    by_status_rows = (
        db.query(TemplateMatch.status, func.count(TemplateMatch.id))
        .group_by(TemplateMatch.status)
        .all()
    )

    by_template_rows = (
        db.query(TemplateMatch.template_id, func.count(TemplateMatch.id))
        .filter(TemplateMatch.template_id.isnot(None))
        .group_by(TemplateMatch.template_id)
        .order_by(func.count(TemplateMatch.id).desc())
        .all()
    )

    by_status = {status: count for status, count in by_status_rows}
    by_template = {template_id: count for template_id, count in by_template_rows}

    return {
        "total": total,
        "by_status": by_status,
        "by_template": by_template,
    }