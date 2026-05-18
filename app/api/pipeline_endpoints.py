# app/api/pipeline_endpoints.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RawMessage, NormalizedMessage, User
from app.pipeline.ingest.gmail_ingest import ingest_gmail_for_household
from app.pipeline.normalize.normalize_job import normalize_pending_for_household

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/ingest/gmail")
def ingest_gmail_my_household(
    max_results_per_user: int = 500,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Stage 0: Ingest bank emails since Jan 1 for ALL users in the current user's household.
    JWT protected. household_id inferred from current_user.
    """
    household_id = str(current_user.household_id)
    return ingest_gmail_for_household(
        db=db,
        household_id=household_id,
        max_results_per_user=max_results_per_user,
    )


@router.post("/normalize")
def normalize_my_household(
    limit: int = 2000,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Stage 1: Normalize pending raw emails for the current user's household.
    JWT protected. household_id inferred.
    """
    household_id = str(current_user.household_id)
    return normalize_pending_for_household(
        db=db,
        household_id=household_id,
        limit=limit,
    )


@router.get("/status")
def pipeline_status_my_household(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Status for current user's household.
    JWT protected. household_id inferred.
    """
    household_id = str(current_user.household_id)

    raw_count = db.execute(
        select(func.count()).select_from(RawMessage).where(RawMessage.household_id == household_id)
    ).scalar_one()

    norm_count = db.execute(
        select(func.count())
        .select_from(NormalizedMessage)
        .join(RawMessage, NormalizedMessage.raw_message_id == RawMessage.id)
        .where(RawMessage.household_id == household_id)
    ).scalar_one()

    users_count = db.execute(
        select(func.count()).select_from(User).where(User.household_id == household_id)
    ).scalar_one()

    return {
        "household_id": household_id,
        "users": users_count,
        "raw_messages": raw_count,
        "normalized_messages": norm_count,
        "pending_normalization": max(raw_count - norm_count, 0),
    }