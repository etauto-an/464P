"""
Persistence layer -- seed.py

Populates the SQLite database with 30 synthetic SKUs for development
and demonstration. Safe to re-run -- clears existing Product and
InventoryState rows before inserting fresh data.

Run from the project root:
    python db/seed.py

Layer: Persistence (db/)
Depends on: db/database.py, db/models.py
"""

import random
import sys
import os

# Add the project root to sys.path so imports work when running directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import SessionLocal, engine
from db.models import Base, Product, InventoryState

# 30 realistic warehouse product names
PRODUCT_NAMES = [
    "Wireless Keyboard",
    "USB-C Hub 7-Port",
    "Mechanical Pencil Set",
    "Notebook A5 Ruled",
    "HDMI Cable 2m",
    "Screen Cleaning Kit",
    "Laptop Stand Aluminium",
    "Mouse Pad XL",
    "Thermal Paste Syringe",
    "Cable Organizer Velcro",
    "Power Strip 6-Outlet",
    "Sticky Notes Pack 400",
    "Whiteboard Marker Set",
    "Label Maker Tape 12mm",
    "Ethernet Cable Cat6 5m",
    "Monitor Arm Single",
    "Webcam Cover Slider 3pk",
    "AA Battery Pack 20",
    "USB Flash Drive 64GB",
    "Bluetooth Headset Mono",
    "Ergonomic Wrist Rest",
    "Cable Clip Adhesive 20pk",
    "Screen Protector Film",
    "Anti-Static Wristband",
    "Insulated Bag Small",
    "Packing Tape Roll 50m",
    "Bubble Wrap Sheet 1m",
    "Barcode Scanner Stand",
    "Receipt Paper Roll 80mm",
    "LED Desk Lamp USB",
]

BIN_PREFIXES = ["A", "B", "C", "D"]


def seed():
    """
    Create all tables and insert 30 synthetic product and inventory rows.

    Physical counts are randomised between 10 and 100 units.
    Reserved counts are 0-20% of physical (rounded), guaranteeing that
    Available = Physical - Reserved is always non-negative.

    Returns:
        None

    Raises:
        Any SQLAlchemy exception propagated to the caller.
    """
    # Create all tables defined in Base.metadata (idempotent if already exist).
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Clear existing seed rows so the script is safely re-runnable.
        db.query(InventoryState).delete()
        db.query(Product).delete()
        db.commit()

        for i, name in enumerate(PRODUCT_NAMES):
            sku = f"SKU-{1000 + i:04d}"

            # Bin location: row letter (A-D), shelf (1-5), position (01-10)
            bin_loc = (
                f"{random.choice(BIN_PREFIXES)}"
                f"{random.randint(1, 5)}-"
                f"{random.randint(1, 10):02d}"
            )

            physical = random.randint(10, 100)
            # Reserve 0-20% of physical stock for open orders.
            reserved = random.randint(0, max(0, int(physical * 0.20)))
            # Invariant: available is always physical minus reserved.
            available = physical - reserved

            db.add(Product(sku=sku, name=name, bin_location=bin_loc))
            db.add(InventoryState(
                sku=sku,
                physical=physical,
                reserved=reserved,
                available=available,
            ))

        db.commit()
        print(f"Seeded {len(PRODUCT_NAMES)} SKUs successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
