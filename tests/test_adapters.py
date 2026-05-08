"""
Adapter layer tests -- test_adapters.py

Verifies the StorefrontAdapter ABC contract and the ShopifyDummyAdapter
concrete implementation. No database or HTTP layer is involved.

Two concerns are tested:
  1. The ABC enforcement: a class that omits an abstract method raises
     TypeError on instantiation, confirming the interface contract is binding.
  2. The dummy adapter's response structure satisfies the contract defined
     in StorefrontAdapter.

Layer tested: Adapter (adapters/)
"""

import pytest

from adapters.base import StorefrontAdapter
from adapters.shopify_dummy import ShopifyDummyAdapter


# ---------------------------------------------------------------------------
# ABC enforcement
# ---------------------------------------------------------------------------

class TestStorefrontAdapterABC:
    """Verifies that the abstract base class enforces its interface contract."""

    def test_cannot_instantiate_abstract_base(self):
        """StorefrontAdapter itself cannot be instantiated (it is abstract)."""
        with pytest.raises(TypeError):
            StorefrontAdapter()

    def test_missing_read_inventory_raises_type_error(self):
        """A subclass that omits read_inventory raises TypeError on instantiation."""
        class MissingRead(StorefrontAdapter):
            def write_inventory(self, sku: str, quantity: int) -> dict:
                return {}

        with pytest.raises(TypeError):
            MissingRead()

    def test_missing_write_inventory_raises_type_error(self):
        """A subclass that omits write_inventory raises TypeError on instantiation."""
        class MissingWrite(StorefrontAdapter):
            def read_inventory(self, sku: str) -> dict:
                return {}

        with pytest.raises(TypeError):
            MissingWrite()

    def test_complete_subclass_instantiates_without_error(self):
        """A subclass that implements both methods instantiates successfully."""
        class FullAdapter(StorefrontAdapter):
            def read_inventory(self, sku: str) -> dict:
                return {"sku": sku, "quantity": 0, "source": "test"}

            def write_inventory(self, sku: str, quantity: int) -> dict:
                return {"sku": sku, "success": True, "message": "ok"}

        adapter = FullAdapter()
        assert isinstance(adapter, StorefrontAdapter)


# ---------------------------------------------------------------------------
# ShopifyDummyAdapter -- read_inventory
# ---------------------------------------------------------------------------

class TestShopifyDummyAdapterReadInventory:
    """Tests for ShopifyDummyAdapter.read_inventory()."""

    @pytest.fixture()
    def adapter(self):
        """Return a fresh ShopifyDummyAdapter instance."""
        return ShopifyDummyAdapter()

    def test_returns_dict(self, adapter):
        """read_inventory returns a dict."""
        result = adapter.read_inventory("SKU-001")
        assert isinstance(result, dict)

    def test_sku_field_matches_input(self, adapter):
        """The returned 'sku' field matches the input SKU."""
        result = adapter.read_inventory("MY-SKU")
        assert result["sku"] == "MY-SKU"

    def test_quantity_is_non_negative_integer(self, adapter):
        """The returned 'quantity' is a non-negative integer."""
        result = adapter.read_inventory("SKU-001")
        assert isinstance(result["quantity"], int)
        assert result["quantity"] >= 0

    def test_source_field_present(self, adapter):
        """The returned dict contains a 'source' key."""
        result = adapter.read_inventory("SKU-001")
        assert "source" in result

    def test_contract_keys_present(self, adapter):
        """All three required contract keys (sku, quantity, source) are present."""
        result = adapter.read_inventory("SKU-CONTRACT")
        assert {"sku", "quantity", "source"}.issubset(result.keys())


# ---------------------------------------------------------------------------
# ShopifyDummyAdapter -- write_inventory
# ---------------------------------------------------------------------------

class TestShopifyDummyAdapterWriteInventory:
    """Tests for ShopifyDummyAdapter.write_inventory()."""

    @pytest.fixture()
    def adapter(self):
        """Return a fresh ShopifyDummyAdapter instance."""
        return ShopifyDummyAdapter()

    def test_returns_dict(self, adapter):
        """write_inventory returns a dict."""
        result = adapter.write_inventory("SKU-001", 10)
        assert isinstance(result, dict)

    def test_contract_keys_present(self, adapter):
        """Response contains all required contract keys."""
        result = adapter.write_inventory("SKU-001", 10)
        assert {"sku", "success", "message"}.issubset(result.keys())

    def test_sku_field_matches_input(self, adapter):
        """The returned 'sku' matches the input SKU."""
        result = adapter.write_inventory("MY-SKU", 5)
        assert result["sku"] == "MY-SKU"

    def test_success_is_true(self, adapter):
        """write_inventory always returns success=True."""
        result = adapter.write_inventory("SKU-001", 10)
        assert result["success"] is True

    def test_success_field_is_bool(self, adapter):
        """The 'success' field is a boolean."""
        result = adapter.write_inventory("SKU-001", 10)
        assert isinstance(result["success"], bool)
