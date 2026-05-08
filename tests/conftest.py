"""
Test configuration -- conftest.py

Provides shared pytest fixtures for all test modules. The central fixture is
an in-memory SQLite database with all ORM tables created fresh for each test
function. This avoids filesystem side effects and guarantees test isolation.

All fixtures in this file are available to every test module without an
explicit import.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base
from db.models import InventoryState, Product


# ---------------------------------------------------------------------------
# In-memory database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_engine():
    """
    Create a fresh in-memory SQLite engine with all tables.

    Yields an engine scoped to one test function. The engine (and all its
    data) is destroyed when the test ends -- no filesystem side effects.

    Yields:
        Engine: SQLAlchemy engine bound to sqlite:///:memory:
    """
    # check_same_thread=False mirrors the production engine configuration.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    # Create every table defined in the ORM metadata.
    Base.metadata.create_all(bind=engine)
    yield engine
    # Teardown: drop all tables and dispose the connection pool.
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """
    Yield a SQLAlchemy session bound to the in-memory engine.

    Each test gets a clean session. The session is closed after the test
    regardless of pass/fail.

    Parameters:
        db_engine: the in-memory engine fixture (injected by pytest).

    Yields:
        Session: active SQLAlchemy session.
    """
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _seed_sku(session, sku: str, physical: int, reserved: int):
    """
    Insert one Product and one InventoryState row for the given SKU.

    Parameters:
        session: active SQLAlchemy session.
        sku (str): SKU identifier.
        physical (int): physical unit count.
        reserved (int): reserved unit count.
    """
    available = physical - reserved
    session.add(Product(sku=sku, name=f"Test Product {sku}", bin_location="A-01"))
    session.add(InventoryState(sku=sku, physical=physical, reserved=reserved, available=available))
    session.commit()


@pytest.fixture()
def seeded_session(db_session):
    """
    Return a db_session pre-loaded with a small set of test SKUs.

    SKUs and counts are chosen to exercise boundary conditions:
        SKU-A  physical=10  reserved=3   available=7   (normal stock)
        SKU-B  physical=5   reserved=5   available=0   (fully reserved, zero available)
        SKU-C  physical=1   reserved=0   available=1   (single unit, nothing reserved)

    Yields:
        Session: the seeded session.
    """
    _seed_sku(db_session, "SKU-A", physical=10, reserved=3)
    _seed_sku(db_session, "SKU-B", physical=5,  reserved=5)
    _seed_sku(db_session, "SKU-C", physical=1,  reserved=0)
    return db_session
