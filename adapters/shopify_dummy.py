"""
Adapter layer -- shopify_dummy.py

Dummy implementation of StorefrontAdapter simulating Shopify inventory API
responses. All responses are generated in-process -- no HTTP calls are made
and no real API credentials are required.

This file is the prototype stand-in for Phase I. A real ShopifyAdapter would
replace this file without requiring any changes to the engine or API layers,
because both sides only reference the StorefrontAdapter abstract interface.

Layer: Adapter (adapters/)
Implements: StorefrontAdapter (adapters/base.py)

# TODO: Phase II -- replace with a real Shopify REST/GraphQL adapter using
# live API credentials, OAuth, and webhook-based event processing.
"""

import random

from adapters.base import StorefrontAdapter


class ShopifyDummyAdapter(StorefrontAdapter):
    """
    Mock Shopify storefront adapter.

    Layer: Adapter
    Implements: StorefrontAdapter

    Simulates the behaviour of a real Shopify inventory integration by
    returning randomised or hardcoded responses. A small configurable
    ERROR_RATE simulates transient storefront API failures.

    All Shopify-specific details (response shape, simulated item IDs,
    error messages) are contained entirely within this class. The engine
    and API layers never see these details.
    """

    # Probability (0.0-1.0) of a simulated transient storefront error.
    ERROR_RATE = 0.05

    def read_inventory(self, sku: str) -> dict:
        """
        Simulate reading the inventory level for a SKU from Shopify.

        Returns a randomised quantity to mimic the realistic scenario where
        the storefront's count has drifted from the warehouse truth --
        which is exactly why a sync operation is needed.

        Parameters:
            sku (str): the SKU to query.

        Returns:
            dict: {"sku": str, "quantity": int, "source": "shopify_dummy"}
        """
        # Adapter interface boundary: response shape is Shopify-specific
        # but must satisfy the StorefrontAdapter contract.
        simulated_qty = random.randint(0, 150)
        return {
            "sku": sku,
            "quantity": simulated_qty,
            "source": "shopify_dummy",
        }

    def write_inventory(self, sku: str, quantity: int) -> dict:
        """
        Simulate pushing an inventory count update to Shopify.

        With probability ERROR_RATE the operation returns a simulated failure
        to demonstrate how the sync log captures error outcomes.

        Parameters:
            sku (str): the SKU whose Available count is being pushed.
            quantity (int): the Available count to set on the storefront.

        Returns:
            dict: {
                "sku": str,
                "success": bool,
                "message": str,
                "shopify_inventory_item_id": str | None  (simulated)
            }

        # Adapter interface boundary: "shopify_inventory_item_id" is a
        # Shopify-specific field. The engine and sync route treat the
        # response as an opaque dict and only inspect "success".
        """
        # Simulate occasional transient failure (e.g., rate limit hit)
        if random.random() < self.ERROR_RATE:
            return {
                "sku": sku,
                "success": False,
                "message": "Simulated transient Shopify API error (rate limited).",
                "shopify_inventory_item_id": None,
            }

        # Simulate a Shopify inventory_item_id that a real adapter would use
        fake_item_id = f"shopify_{sku}_{random.randint(100_000, 999_999)}"
        return {
            "sku": sku,
            "success": True,
            "message": f"Inventory updated to {quantity} units on Shopify.",
            "shopify_inventory_item_id": fake_item_id,
        }
