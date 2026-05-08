"""
Persistence layer -- database.py

Configures the SQLAlchemy engine and session factory for the SQLite database.
This is the single point of connection configuration for the entire application.
All other modules that need a database session import get_db() from here.

Layer: Persistence (db/)
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import NullPool

# Absolute path derived from this file's location so the database is found
# regardless of the working directory the process is started from.
_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventory.db")
DATABASE_URL = f"sqlite:///{_DB_PATH}"

# NullPool opens a fresh SQLite connection for each session and closes it when
# the session ends. This is required for SQLite + multi-threaded uvicorn:
# StaticPool shares one underlying sqlite3* handle across all threads, which
# causes memory corruption (SIGSEGV) when two requests execute SQL
# concurrently. NullPool eliminates sharing entirely -- each request gets its
# own connection, so there is no cross-thread state to corrupt.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
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
