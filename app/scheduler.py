from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User
from app.gmail.gmail_client import fetch_and_store_transactions


def sync_households_job():
    db: Session = SessionLocal()

    try:
        users = db.query(User).all()

        for user in users:
            fetch_and_store_transactions(db, user.id)

        print("Household sync completed.")

    except Exception as e:
        print("Sync error:", e)

    finally:
        db.close()


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(sync_households_job, "interval", minutes=10)
    scheduler.start()