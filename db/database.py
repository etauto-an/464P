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
from sqlalchemy.pool import StaticPool

# Absolute path derived from this file's location so the database is found
# regardless of the working directory the process is started from.
_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventory.db")
DATABASE_URL = f"sqlite:///{_DB_PATH}"

# StaticPool shares one connection across all threads. This is the correct
# pool for SQLite + FastAPI: FastAPI runs sync handlers in a thread pool, and
# SQLAlchemy's default SingletonThreadPool gives each thread its own
# connection -- if one thread's connection ends up in a bad state, every
# other request routed to it gets a 500. StaticPool serialises all access
# through a single connection, eliminating that problem.
# check_same_thread=False is still required so SQLite accepts calls from
# threads other than the one that opened the connection.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
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
