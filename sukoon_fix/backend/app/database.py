"""
Sukoon — Database configuration.

Uses SQLite for local/prototype development. The models are written with
standard SQLAlchemy types (no SQLite-only features) so the same schema can
be pointed at PostgreSQL for a production deployment simply by changing
DATABASE_URL (see README).
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_URL = os.environ.get("SUKOON_DATABASE_URL", f"sqlite:///{BASE_DIR}/sukoon.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
