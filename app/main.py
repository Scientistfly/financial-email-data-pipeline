import os
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from app.database import engine
from app.models import Base
from app.parser import parse_email
from app.database import SessionLocal
from app.models import Transaction
from fastapi import Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from app.gmail.gmail_client import get_transactions
from fastapi.responses import RedirectResponse
from app.auth import create_flow
from app.auth import save_oauth_credentials
from google.oauth2.credentials import Credentials
import json
from fastapi import Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Oauth_Creds
import uuid
from app.gmail.gmail_client import build_gmail_service
from app.gmail.gmail_client import fetch_and_store_transactions
from googleapiclient.discovery import build
from app.models import User
from app.models import Household
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.security import hash_password, verify_password, create_access_token
from fastapi import HTTPException, status
from app.dependencies import get_current_user
from uuid import UUID
from typing import Optional
from app.scheduler import start_scheduler
from app.models import MerchantAlias
from app.models import DebugEmail
from app.gmail.gmail_client import build_test_query
from app.gmail.gmail_client import extract_email_body
from bs4 import BeautifulSoup
import base64
from app.class_engine import classify_transaction
from app.parser import clean_email_body
from sqlalchemy import text
from app.api.pipeline_endpoints import router as pipeline_router
from app.api.routes.pipeline_detect import router as pipeline_detect_router


from pydantic import BaseModel

class RegisterRequest(BaseModel):
    email: str
    password: str
    household_id: Optional[UUID] = None
    household_name: Optional[str] = None


#Base.metadata.create_all(bind=engine)

app = FastAPI()
app.include_router(pipeline_router)
app.include_router(pipeline_detect_router)

@app.get("/")
def root():
    return {"message": "Finanzas App Backend Running"}

# Test the connection
try:
    with engine.connect() as connection:
        print("Connection successful!")
except Exception as e:
    print(f"Failed to connect: {e}")


@app.get("/test-save")
def test_save():
    sample_email = """
    Estimado cliente,
    Banco del Pacifico le informa que a las 19:26 se debito de
    su cta terminada en 8426 el valor de $2.12, por
    CONSUMO NACIONAL en MEGAMAXI.
    """

    parsed = parse_email(sample_email)

    db = SessionLocal()

    transaction = Transaction(
        amount=parsed["amount"],
        merchant=parsed["merchant"],
        transaction_type=parsed["transaction_type"],
        card_name=parsed["card_name"]
    )

    db.add(transaction)
    db.commit()
    db.close()

    return {"message": "Transaction saved!"}

@app.post("/parse-email")
async def parse_email_endpoint(request: Request):
    body = await request.json()
    parsed = parse_email(body["email_text"])
    return parsed

templates = Jinja2Templates(directory="templates")

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):

    db = SessionLocal()
    transactions = db.query(Transaction).all()
    db.close()

    total_expenses = sum(t.amount for t in transactions if t.transaction_type == "expense")
    total_income = sum(t.amount for t in transactions if t.transaction_type == "income")

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "transactions": transactions,
        "total_expenses": total_expenses,
        "total_income": total_income
    })

@app.get("/test-gmail")
def test_gmail():
    emails = get_transactions()
    return {"emails": emails}

@app.get("/auth/login")
def auth_login():
    flow = create_flow()

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt="consent"     # ✅ force refresh token
    )

    return RedirectResponse(authorization_url)

#Temporal User ID
TEMP_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

@app.get("/auth/callback")
async def auth_callback(request: Request, db:Session = Depends(get_db),):

    flow = create_flow()

    flow.fetch_token(authorization_response=str(request.url))

    credentials = flow.credentials

    # Build temporary service to get user email
    oauth_service = build("oauth2", "v2", credentials=credentials)
    user_info = oauth_service.userinfo().get().execute()

    email = user_info["email"]
    name = user_info.get("name")

    # 1️⃣ Get or create default household
    household = db.query(Household).filter(
        Household.name == "BB Family Household"
    ).first()

    if not household:
        household = Household(name="BB Family Household")
        db.add(household)
        db.commit()
        db.refresh(household)

    user = db.query(User).filter(User.email == email).first()

    if not user:
        user = User(
            email=email,
            name=name,
            household_id=household.id
            )
        db.add(user)
        db.commit()
        db.refresh(user)

    

    save_oauth_credentials(
    db=db,
    #user_id=TEMP_USER_ID,
    #user_id=current_user.id,
    user_id=user.id,
    provider="google",
    refresh_token=credentials.refresh_token,
    access_token=credentials.token,
    expiry=credentials.expiry,
    scopes=" ".join(credentials.scopes) if credentials.scopes else None,
    )

    # Save token to file
    # open("token.json", "w") as token:
    #    token.write(credentials.to_json())

    return {"message": "Authentication successful and credentials stored"}

@app.get("/test-db")
def test_db(db: Session = Depends(get_db)):
    creds = db.query(Oauth_Creds).all()
    return creds


@app.get("/gmail/sync-all")
def sync_all_users(db: Session = Depends(get_db)):

    users = db.query(User).all()

    results = []

    for user in users:
        saved = fetch_and_store_transactions(db, user.id)
        results.append({
            "user": user.email,
            "saved": saved
        })

    return results

@app.get("/household/summary")
def household_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    household = db.query(Household).filter(
        Household.name == "BB Family Household"
    ).first()

    if not household:
        return {
            "error": "No household found. Connect a user first."
        }

    users = db.query(User).filter(
        User.household_id == household.id
    ).all()

    user_ids = [u.id for u in users]

    transactions = db.query(Transaction).filter(
        Transaction.user_id.in_(user_ids)
    ).all()

    return {
        "household": household.name,
        "members": [u.email for u in users],
        "total_transactions": len(transactions)
    }

@app.post("/register")
def register(request: RegisterRequest, db: Session = Depends(get_db)):

    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    # 🔹 CASE 1: Join existing household
    if request.household_id:

        household = db.query(Household).filter(
            Household.id == request.household_id
        ).first()

        if not household:
            raise HTTPException(
                status_code=400,
                detail="Household not found"
            )

        household_id = household.id

    # 🔹 CASE 2: Create new household
    else:
        if not request.household_name:
            raise HTTPException(
                status_code=400,
                detail="Household name is required to create a new household"
            )
        new_household = Household(
            id=uuid.uuid4(),
            name=request.household_name
        )
        db.add(new_household)
        db.commit()
        db.refresh(new_household)

        household_id = new_household.id

    hashed_password = hash_password(request.password)

    new_user = User(
        email=request.email,
        hashed_password=hashed_password,
        household_id=household_id
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "User created successfully",
        "household_id": str(household_id)
    }

@app.post("/login")
def login(request: RegisterRequest, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.email == request.email).first()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "household_id": str(user.household_id)
        }
    )

    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/protected")
def protected_route(current_user: dict = Depends(get_current_user)):
    return {
        "message": "Access granted",
        "user": current_user
    }

@app.get("/household/sync")
def sync_household(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    # Convert string from JWT back to UUID
    household_id = UUID(current_user["household_id"])

    # 1️⃣ Get all users in same household
    users = db.query(User).filter(
        User.household_id == household_id
    ).all()

    results = []

    # 2️⃣ Sync each user's Gmail
    for user in users:
        saved = fetch_and_store_transactions(db, user.id)

        results.append({
            "user": user.email,
            "saved_count": len(saved)
        })

    return {
        "household_members": [user.email for user in users],
        "members_synced": results
    }

@app.on_event("startup")
def start_background_tasks():
    start_scheduler()

@app.post("/transactions/{transaction_id}/correct")
def correct_transaction(
    transaction_id: str,
    normalized_merchant: str,
    category: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    household_id = current_user.household_id

    # 1️⃣ Save alias rule
    alias = MerchantAlias(
        household_id=current_user.household_id,
        raw_text=transaction.merchant,   # store original
        normalized_name=normalized_merchant,
        default_category=category
    )

    db.add(alias)

    # 2️⃣ Update transaction
    transaction.merchant = normalized_merchant
    transaction.category = category

    db.commit()

    return {"message": "Correction saved and learning updated"}



@app.get("/gmail/debug")
def debug_gmail(current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):

    service = build_gmail_service(db, current_user.id)

    results = service.users().messages().list(
        userId="me",
        q=build_test_query(),
        maxResults=100
    ).execute()

    messages = results.get("messages", [])
    #print("Messages found:", len(messages))  # para debug
    output = []

    for msg in messages:
        full_msg = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="full"
        ).execute()

        #print("Processing message:", msg["id"])   #para debug
        payload = full_msg["payload"]
        #print(full_msg["payload"]["mimeType"])   # para debug
        body_data = extract_email_body(payload)  # your existing logic
        #print("Has body:", bool(body_data))      # para debug

        if not body_data:
            print("No body found for message:", msg["id"])
            continue

        try:
            decoded_body = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
        except Exception as e:
            print("Decode error:", e)
            continue

        decoded_body = clean_email_body(decoded_body)
        print("CLEANED BODY START -----")
        print(decoded_body[:400])
        print("CLEANED BODY END -----")
        parsed = parse_email(decoded_body)

        #print("Parsed result:", parsed)   #para debug

        '''
        if parsed["type"] == "transaction":
            parsed = classify_transaction(
                db,
                current_user.household_id,
                parsed
            )
        '''

        if parsed["type"] == "ignore" or (
            (parsed.get("amount") is None or parsed.get("date") is None) and parsed["type"] != "ignore_only_info"
        ):
            if parsed["type"] == "ignore":
                reason = "ignore"
            elif parsed.get("date") is None and parsed.get("amount") is None:
                reason = "date and amount"
            elif parsed.get("date") is None:
                reason = "date"
            elif parsed.get("amount") is None:
                reason = "amount"
            debug_email = DebugEmail(
                user_id=current_user.id,
                raw_body=decoded_body,
                message_id=msg["id"],
                reason_fail = reason
            )
            db.add(debug_email)
            db.commit()

        output.append({
            "id": msg["id"],
            "parsed": parsed,
            "raw_preview": decoded_body[:500] if parsed["type"] == "ignore" or ((parsed.get("amount") is None or parsed.get("date") is None) and parsed["type"] != "ignore_only_info") else None
        })

    return output

@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    value = db.execute(text("select 1")).scalar_one()
    return {"db": "ok", "value": value}