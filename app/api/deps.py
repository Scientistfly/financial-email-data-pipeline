# app/api/deps.py
import os
from fastapi import Header, HTTPException

def require_pipeline_admin(x_admin_token: str = Header(..., alias="X-ADMIN-TOKEN")):
    expected = os.getenv("PIPELINE_ADMIN_TOKEN")
    if not expected or x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True