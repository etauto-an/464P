"""
Persistence layer -- database.py

Configures the SQLAlchemy engine and session factory for the SQLite database.
This is the single point of connection configuration for the entire application.
All other modules that need a database session import get_db() from here.

Layer: Persistence (db/)
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# SQLite file stored at the project root alongside the application code.
DATABASE_URL = "sqlite:///./inventory.db"

# check_same_thread=False is required for SQLite when used with FastAPI's
# default (non-async) thread model; SQLite's default True would reject
# accesses from any thread other than the creating thread.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# autocommit=False: transactions are explicit (committed via db.commit()).
# autoflush=False: pending changes are not flushed to the DB before each query
# unless we call db.flush() explicitly, giving the engine full control.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """
    Declarative base class for all SQLAlchemy ORM models in this project.

    Layer: Persistence
    All model classes inherit from this base so that Base.metadata.create_all()
    can discover and create every table in one call.
    """
    pass


def get_db():
    """
    FastAPI dependency that yields a database session and guarantees cleanup.

    Yields:
        Session: an active SQLAlchemy database session scoped to one request.

    The finally block ensures the session is closed (and the connection returned
    to the pool) even if the route handler raises an exception.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
