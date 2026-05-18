# app/api/routes/pipeline_detect.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.pipeline.detect.service import detect_pending_templates, redetect_all_templates
from app.pipeline.detect.report import get_template_detection_report

router = APIRouter(prefix="/pipeline/detect", tags=["pipeline-detect"])


@router.post("/run")
def run_template_detection(
    limit: int | None = Query(default=None, ge=1),
    redetect: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    if redetect:
        result = redetect_all_templates(db=db, limit=limit)
    else:
        result = detect_pending_templates(db=db, limit=limit)

    return {
        "status": "ok",
        "mode": "redetect_all" if redetect else "detect_pending",
        **result,
    }


@router.get("/report")
def template_detection_report(db: Session = Depends(get_db)):
    return get_template_detection_report(db)