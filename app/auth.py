import os
from google_auth_oauthlib.flow import Flow
from datetime import datetime
import pytz
from app.database import SessionLocal
from app.models import Oauth_Creds
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db

ecuador_tz = pytz.timezone("America/Guayaquil")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid"
]

def create_flow():
    flow = Flow.from_client_secrets_file(
        os.getenv("GOOGLE_CREDENTIALS_PATH"),
        scopes=SCOPES,
        redirect_uri='http://localhost:8000/auth/callback'
    )
    return flow

def save_oauth_credentials(
    db: Session,
    user_id,
    provider: str,
    access_token: str,
    refresh_token: str | None,
    expiry: datetime | None,
    scopes: str | None,
):
    """
    Save or update OAuth credentials safely.

    - Does NOT overwrite refresh_token if Google does not return one
    - Uses ORM instead of raw insert
    """

    existing = (
        db.query(Oauth_Creds)
        .filter(
            Oauth_Creds.user_id == user_id,
            Oauth_Creds.provider == provider,
        )
        .first()
    )

    if existing:
        # Always update access token + expiry
        existing.access_token = access_token
        existing.expiry = expiry
        existing.scopes = scopes
        existing.updated_at = datetime.utcnow()

        # Only update refresh_token if Google actually returned one
        if refresh_token:
            existing.refresh_token = refresh_token

    else:
        new_creds = Oauth_Creds(
            user_id=user_id,
            provider=provider,
            access_token=access_token,
            refresh_token=refresh_token,
            expiry=expiry,
            scopes=scopes,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(new_creds)

    db.commit()


def get_oauth_credentials(db: Session, user_id: str, provider: str):
    stmt = select(Oauth_Creds).where(
        Oauth_Creds.user_id == user_id,
        Oauth_Creds.provider == provider
    )

    result = db.execute(stmt).scalar_one_or_none()
    return result