"""
simulate_day.py

Simulates a day's worth of warehouse activity against the running FastAPI server.
Fires a sequence of pick and damage events across all SKUs, mimicking a realistic
shift: multiple rounds of order fulfillment with occasional damage write-offs.

Run AFTER starting the backend:
    uvicorn api.main:app --reload

Then in a separate terminal:
    python simulate_day.py

Watch the dashboard at http://localhost:5173 while the script runs.

Configuration constants at the top of the file control pace, volume, and
damage rate. Adjust them to lengthen or shorten the demo.
"""

import time
import random
import sys
import urllib.request
import urllib.error
import json

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = "http://localhost:8000"

# Number of simulated order-fulfillment rounds (each round processes a batch
# of SKUs). More rounds = longer demo.
NUM_ROUNDS = 8

# Fraction of SKUs picked per round (0.0-1.0). 0.4 means ~12 of 30 SKUs per round.
PICK_FRACTION = 0.4

# Maximum units to pick per SKU per round. Kept small so Reserved isn't
# exhausted in the first round.
MAX_PICK_QTY = 3

# Probability that any given SKU suffers a damage event in a round.
DAMAGE_RATE = 0.08

# Maximum units to write off in a single damage report.
MAX_DAMAGE_QTY = 2

# Seconds to wait between individual API calls within a round.
# Increase this to slow the demo down so the row flashes are visible.
INTER_EVENT_DELAY = 0.3

# Seconds to wait between rounds.
INTER_ROUND_DELAY = 1.5


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def get(path: str) -> dict:
    """
    Send a GET request to the API and return the parsed JSON response.

    Parameters:
        path (str): API path, e.g. '/inventory'.

    Returns:
        dict or list: parsed JSON response body.

    Raises:
        SystemExit: if the request fails or the server is unreachable.
    """
    url = API_BASE + path
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        print(f"\n[ERROR] Could not reach {url}: {exc}")
        print("        Is the backend running? (uvicorn api.main:app --reload)")
        sys.exit(1)


def post(path: str, body: dict) -> tuple:
    """
    Send a POST request with a JSON body and return (status_code, parsed_body).

    Parameters:
        path (str): API path, e.g. '/events/pick'.
        body (dict): request payload, serialised to JSON.

    Returns:
        tuple: (int status_code, dict response_body)
    """
    url = API_BASE + path
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        # 4xx responses still carry a JSON body with the error detail
        return exc.code, json.loads(exc.read().decode())
    except urllib.error.URLError as exc:
        print(f"\n[ERROR] Could not reach {url}: {exc}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def fetch_inventory() -> list:
    """
    Fetch the current inventory state for all SKUs.

    Returns:
        list[dict]: all SKU rows with physical/reserved/available counts.
    """
    return get("/inventory")


def run_round(round_num: int, inventory: list) -> list:
    """
    Execute one round of simulated warehouse activity.

    Selects a random subset of SKUs for picking. SKUs with Reserved = 0 are
    skipped (no committed orders to fulfil). A small fraction of SKUs also
    receive a damage report.

    Parameters:
        round_num (int): 1-based round number, used for display only.
        inventory (list[dict]): current state for all SKUs.

    Returns:
        list[str]: SKUs that were modified this round (for the caller to
                   selectively re-fetch if needed).
    """
    pickable = [s for s in inventory if s["reserved"] > 0]
    damageable = [s for s in inventory if s["available"] > 0]

    # Choose a random subset to pick this round
    pick_count = max(1, int(len(pickable) * PICK_FRACTION))
    pick_targets = random.sample(pickable, min(pick_count, len(pickable)))

    # Choose a small random subset for damage reports
    damage_count = max(0, int(len(damageable) * DAMAGE_RATE))
    damage_targets = random.sample(damageable, min(damage_count, len(damageable)))

    print(f"\n--- Round {round_num} ---  "
          f"picks: {len(pick_targets)}  damages: {len(damage_targets)}")

    modified = []

    # --- Pick events ---
    for sku_row in pick_targets:
        sku = sku_row["sku"]
        # Pick a quantity that won't exceed current Reserved
        qty = random.randint(1, min(MAX_PICK_QTY, sku_row["reserved"]))

        status, resp = post("/events/pick", {"sku": sku, "quantity": qty})

        if status == 200:
            print(f"  PICK    {sku}  qty={qty}  "
                  f"physical={resp['physical']}  "
                  f"reserved={resp['reserved']}  "
                  f"available={resp['available']}")
                modified.append(sku)
        else:
            # Unexpected rejection -- log and continue
            print(f"  PICK    {sku}  qty={qty}  REJECTED: {resp.get('detail', resp)}")

        time.sleep(INTER_EVENT_DELAY)

    # --- Damage reports ---
    for sku_row in damage_targets:
        sku = sku_row["sku"]
        qty = random.randint(1, min(MAX_DAMAGE_QTY, sku_row["available"]))

        status, resp = post("/events/damage", {"sku": sku, "quantity": qty})

        if status == 200:
            print(f"  DAMAGE  {sku}  qty={qty}  "
                  f"physical={resp['physical']}  "
                  f"available={resp['available']}")
                modified.append(sku)
        else:
            print(f"  DAMAGE  {sku}  qty={qty}  REJECTED: {resp.get('detail', resp)}")

        time.sleep(INTER_EVENT_DELAY)

    return modified


def print_summary(before: list, after: list) -> None:
    """
    Print a before/after summary table comparing inventory state at the
    start and end of the simulation.

    Parameters:
        before (list[dict]): inventory snapshot taken before the simulation.
        after  (list[dict]): inventory snapshot taken after the simulation.
    """
    before_map = {s["sku"]: s for s in before}

    print("\n" + "=" * 70)
    print(f"{'SKU':<12} {'Name':<28} {'Phys':>5} {'Res':>5} {'Avail':>6}  {'Change':>8}")
    print("-" * 70)

    total_removed = 0

    for row in after:
        sku = row["sku"]
        prev = before_map.get(sku, row)
        delta_phys = row["physical"] - prev["physical"]  # negative means units left

        changed = delta_phys != 0
        marker = f"phys {delta_phys:+d}" if changed else ""
        total_removed += max(0, prev["physical"] - row["physical"])

        print(f"  {sku:<12} {(row['name'] or ''):<28} "
              f"{row['physical']:>5} {row['reserved']:>5} {row['available']:>6}  {marker}")

    print("=" * 70)
    print(f"Total physical units removed: {total_removed}")
    print()


def main():
    """
    Entry point. Runs NUM_ROUNDS of simulated warehouse activity, printing
    progress to stdout and leaving the database in its post-simulation state.
    """
    print("=" * 70)
    print("  Warehouse Day Simulation")
    print(f"  {NUM_ROUNDS} rounds  |  ~{int(PICK_FRACTION*100)}% SKUs picked per round  |  {int(DAMAGE_RATE*100)}% damage rate")
    print("=" * 70)

    # Snapshot state before the simulation for the final summary
    print("\nFetching initial inventory state…")
    inventory_before = fetch_inventory()

    pickable_count = sum(1 for s in inventory_before if s["reserved"] > 0)
    print(f"  {len(inventory_before)} SKUs total  |  {pickable_count} have reserved stock (pickable)")

    inventory = list(inventory_before)  # working copy updated each round

    for round_num in range(1, NUM_ROUNDS + 1):
        run_round(round_num, inventory)
        # Re-fetch full state so next round uses current counts
        inventory = fetch_inventory()
        if round_num < NUM_ROUNDS:
            time.sleep(INTER_ROUND_DELAY)

    # Final sync to push all updated Available counts to the storefront adapter
    print("\nTriggering end-of-day sync…")
    status, sync_resp = post("/sync", {})
    if status == 200:
        print(f"  Sync complete: {sync_resp['synced']} succeeded, {sync_resp['errors']} errors")
    else:
        print(f"  Sync failed: {sync_resp}")

    # Print before/after summary
    inventory_after = fetch_inventory()
    print_summary(inventory_before, inventory_after)
    print("Simulation complete. Check the dashboard for the final state.")


if __name__ == "__main__":
    main()
