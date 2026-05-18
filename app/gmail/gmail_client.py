import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from sqlalchemy.orm import Session
from app.models import Oauth_Creds
from datetime import datetime, timedelta
import pytz
import base64
from email import message_from_bytes
from app.parser import parse_email
from app.models import Transaction
from bs4 import BeautifulSoup
from app.class_engine import classify_transaction
from app.models import User


def build_gmail_service(db: Session, user_id: str):

    # 1️⃣ Load stored credentials from DB
    stored_creds = (
        db.query(Oauth_Creds)
        .filter(
            Oauth_Creds.user_id == user_id,
            Oauth_Creds.provider == "google"
        )
        .first()
    )

    if not stored_creds:
        raise Exception("Google OAuth credentials not found.")

    # 2️⃣ Rebuild Credentials object
    creds = Credentials(
        token=stored_creds.access_token,
        refresh_token=stored_creds.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        scopes=stored_creds.scopes.split()
    )

    # 3️⃣ Auto-refresh if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

        # 4️⃣ Update DB with new access token + expiry
        stored_creds.access_token = creds.token
        stored_creds.expiry = creds.expiry
        stored_creds.updated_at = datetime.utcnow()

        db.commit()

    # 5️⃣ Build Gmail API service
    service = build("gmail", "v1", credentials=creds)

    return service


ecuador_tz = pytz.timezone("America/Guayaquil")

def build_query():
    now = datetime.now(ecuador_tz)
    today = now.date()
    yesterday = today - timedelta(days=1)
    after_date = yesterday.strftime("%Y/%m/%d")
    before_date = today.strftime("%Y/%m/%d")
    return ( "(from:Notificacion@bancomatico.com.ec OR "
             "from:notificaciones@infopacificard.com.ec) "
               f"after:{after_date} before:{before_date}" 
            )
    
def build_test_query():
    return ( "(" "from:notificaciones@pacificard.com.ec OR "
             "from:intermail@bancopacifico.ec OR "
               "from:notificaciones@infopacificard.com.ec OR "
                 "from:estadodecuenta@pacificard.com.ec" ")" 
            )

def get_email_body(service, message_id):
    message = service.users().messages().get(
        userId='me',
        id=message_id,
        format='raw'
    ).execute()

    raw_msg = base64.urlsafe_b64decode(message['raw'])
    mime_msg = message_from_bytes(raw_msg)

    if mime_msg.is_multipart():
        for part in mime_msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode()

    return mime_msg.get_payload(decode=True).decode()

def get_transactions(service):
    query = build_query()

    results = service.users().messages().list(
        userId='me',
        q=query
    ).execute()

    messages = results.get('messages', [])

    email_bodies = []

    for msg in messages:
        body = get_email_body(service, msg['id'])
        email_bodies.append(body)

    return email_bodies

def extract_email_body(payload):

    # Prefer plain text
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return payload["body"]["data"]

    # Fallback to HTML
    if payload.get("mimeType") == "text/html" and payload.get("body", {}).get("data"):
        return payload["body"]["data"]

    if "parts" in payload:
        for part in payload["parts"]:
            result = extract_email_body(part)
            if result:
                return result

    return None

def fetch_and_store_transactions(db: Session, user_id: str):

    # 1️⃣ Load user from DB
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise Exception("User not found")

    if not user.household_id:
        raise Exception("User does not belong to a household")

    # 2️⃣ Build Gmail service
    service = build_gmail_service(db, user_id)

    test_query = build_test_query()

    results = service.users().messages().list(
        userId="me",
        q=test_query,
        maxResults=10
    ).execute()

    messages = results.get("messages", [])
    print("Found messages:", len(messages))

    saved_transactions = []

    for msg in messages:
        msg_id = msg["id"]

        # Prevent duplicate processing
        existing = db.query(Transaction).filter(
            Transaction.gmail_message_id == msg_id
        ).first()

        if existing:
            continue

        # 3️⃣ Fetch full message
        full_msg = service.users().messages().get(
            userId="me",
            id=msg_id,
            format="full"
        ).execute()

        payload = full_msg["payload"]
        body_data = extract_email_body(payload)

        if not body_data:
            print("No body found for message:", msg["id"])
            continue

        try:
            decoded_body = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
        except Exception as e:
            print("Decode error:", e)
            continue

        # Convert HTML to text
        if "<html" in decoded_body.lower():
            soup = BeautifulSoup(decoded_body, "html.parser")
            decoded_body = soup.get_text()

        # 4️⃣ Parse
        parsed = parse_email(decoded_body)

        if not parsed:
            continue

        # Ignore non-transactions
        if parsed["type"] != "transaction":
            continue

        # 5️⃣ Classify using household model
        parsed = classify_transaction(db, user.household_id, parsed)

        print("Parsed result:", parsed)

        # 6️⃣ Save transaction
        transaction = Transaction(
            user_id=user.id,
            household_id=user.household_id,  # IMPORTANT
            amount=parsed["amount"],
            merchant=parsed["merchant_normalized"],
            transaction_type=parsed["transaction_type"],
            category=parsed["category"],
            subcategory=parsed["subcategory"],
            confidence=parsed["confidence"],
            gmail_message_id=msg_id
        )

        db.add(transaction)
        saved_transactions.append(parsed)

    db.commit()

    return saved_transactions