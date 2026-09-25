import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Create a .env file in the project root."
    )

# Keep plain PostgreSQL URLs on the driver declared in requirements.txt.
# SQLAlchemy 2.1 otherwise defaults to psycopg3, which is not installed here.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(DATABASE_URL, echo=False)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    """FastAPI dependency to yield an isolated DB session per HTTP request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
