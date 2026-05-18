# app/api/routes/pipeline_discovery.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.pipeline.discovery.service import cluster_unassigned_messages
from app.pipeline.discovery.report import get_discovery_report, get_discovered_types_with_examples

router = APIRouter(prefix="/pipeline/discovery", tags=["pipeline-discovery"])


@router.post("/run")
def run_discovery(
    limit: int | None = Query(default=None, ge=1),
    similarity_threshold: float = Query(default=0.92, ge=0.0, le=1.0),
    maybe_threshold: float = Query(default=0.80, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
):
    return cluster_unassigned_messages(
        db=db,
        limit=limit,
        similarity_threshold=similarity_threshold,
        maybe_threshold=maybe_threshold,
    )


@router.get("/report")
def discovery_report(db: Session = Depends(get_db)):
    return get_discovery_report(db)


@router.get("/examples")
def discovery_examples(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return get_discovered_types_with_examples(db=db, limit=limit)