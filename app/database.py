import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
#from sqlalchemy.pool import NullPool
from dotenv import load_dotenv
from sqlalchemy.orm import Session





# Load environment variables from .env
load_dotenv()

#DATABASE_URL = os.getenv("DATABASE_URL") #Metodo ChatGPT

# Fetch variables
USER = os.getenv("USER")
PASSWORD = os.getenv("PASSWORD")
HOST = os.getenv("HOST")
PORT = os.getenv("PORT2")
DBNAME = os.getenv("DBNAME")

# Construct the SQLAlchemy connection string
DATABASE_URL = f"postgresql+psycopg2://{USER}:{PASSWORD}@{HOST}:{PORT}/{DBNAME}?sslmode=require"

# Create the SQLAlchemy engine
#engine = create_engine(DATABASE_URL)
# If using Transaction Pooler or Session Pooler, we want to ensure we disable SQLAlchemy client side pooling -
# https://docs.sqlalchemy.org/en/20/core/pooling.html#switching-pool-implementations
# engine = create_engine(DATABASE_URL, poolclass=NullPool)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,     # avoids stale pooled connections
    pool_size=5,
    max_overflow=5,
    pool_recycle=1800,      # recycle connections periodically
)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()