"""
Adapter layer -- base.py

Defines the abstract storefront interface that all platform adapters must
implement. The reconciliation engine and API routes interact only with this
interface; they have no knowledge of any concrete storefront platform.

This design guarantees that swapping the dummy Shopify adapter for a real one
requires zero changes to the engine or API layers.

Layer: Adapter (adapters/)
"""

from abc import ABC, abstractmethod


class StorefrontAdapter(ABC):
    """
    Abstract base class for all storefront integration adapters.

    Layer: Adapter

    Any concrete adapter (real or mock) must subclass this and implement
    both abstract methods. The engine calls only this interface type.

    Contract:
        read_inventory(sku)  -> dict with at least {"sku", "quantity", "source"}
        write_inventory(sku, quantity) -> dict with at least {"sku", "success", "message"}
    """

    @abstractmethod
    def read_inventory(self, sku: str) -> dict:
        """
        Read the current inventory level for a SKU from the storefront.

        Parameters:
            sku (str): the SKU to query.

        Returns:
            dict: {"sku": str, "quantity": int, "source": str}
                  Additional keys are adapter-specific and may be ignored
                  by the engine.

        Raises:
            NotImplementedError: if not overridden by a subclass.
        """
        ...

    @abstractmethod
    def write_inventory(self, sku: str, quantity: int) -> dict:
        """
        Push the current Available count for a SKU to the storefront.

        Parameters:
            sku (str): the SKU whose count is being synced.
            quantity (int): the Available count to push to the storefront.

        Returns:
            dict: {"sku": str, "success": bool, "message": str}
                  Additional keys are adapter-specific.

        Raises:
            NotImplementedError: if not overridden by a subclass.
        """
        ...
