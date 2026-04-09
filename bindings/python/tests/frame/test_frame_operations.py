"""Tests for ActuarialFrame join, filter, rename, drop, sort methods."""

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame


@pytest.fixture()
def sample_af():
    """Create a sample ActuarialFrame for testing."""
    return ActuarialFrame({
        "policy_id": ["P001", "P002", "P003"],
        "product_code": ["TERM", "WL", "TERM"],
        "issue_age": [30, 45, 55],
        "status": ["IF", "LAPSED", "IF"],
    })


class TestJoin:
    def test_join_adds_columns(self, sample_af):
        params = pl.DataFrame({"product_code": ["TERM", "WL"], "rate": [0.05, 0.08]})
        result = sample_af.join(params, on="product_code")
        collected = result.collect()
        assert "rate" in collected.columns
        assert sorted(collected["rate"].to_list()) == [0.05, 0.05, 0.08]

    def test_join_returns_self(self, sample_af):
        params = pl.DataFrame({"product_code": ["TERM"], "rate": [0.05]})
        result = sample_af.join(params, on="product_code")
        assert result is sample_af

    def test_join_with_left_right_on(self):
        af = ActuarialFrame({"id": [1, 2], "val": [10, 20]})
        other = pl.DataFrame({"key": [1, 2], "extra": ["a", "b"]})
        af = af.join(other, left_on="id", right_on="key")
        collected = af.collect()
        assert "extra" in collected.columns

    def test_join_updates_column_order(self, sample_af):
        params = pl.DataFrame({"product_code": ["TERM", "WL"], "new_col": [1, 2]})
        sample_af.join(params, on="product_code")
        assert "new_col" in sample_af.get_column_order()

    def test_join_with_dataframe(self, sample_af):
        params = pl.DataFrame({"product_code": ["TERM", "WL"], "rate": [0.05, 0.08]})
        sample_af.join(params, on="product_code")
        assert "rate" in sample_af.collect().columns

    def test_join_with_lazyframe(self, sample_af):
        params = pl.DataFrame({"product_code": ["TERM", "WL"], "rate": [0.05, 0.08]}).lazy()
        sample_af.join(params, on="product_code")
        assert "rate" in sample_af.collect().columns


class TestFilter:
    def test_filter_reduces_rows(self, sample_af):
        result = sample_af.filter(pl.col("status") == "IF")
        collected = result.collect()
        assert collected.height == 2
        assert collected["status"].to_list() == ["IF", "IF"]

    def test_filter_returns_self(self, sample_af):
        result = sample_af.filter(pl.col("status") == "IF")
        assert result is sample_af

    def test_filter_by_numeric(self, sample_af):
        result = sample_af.filter(pl.col("issue_age") >= 45)
        collected = result.collect()
        assert collected.height == 2


class TestRename:
    def test_rename_changes_column_names(self):
        af = ActuarialFrame({"Issue Age": [30], "Sum Assured": [100000]})
        af = af.rename({"Issue Age": "issue_age", "Sum Assured": "sum_assured"})
        collected = af.collect()
        assert "issue_age" in collected.columns
        assert "sum_assured" in collected.columns
        assert "Issue Age" not in collected.columns

    def test_rename_returns_self(self):
        af = ActuarialFrame({"a": [1]})
        result = af.rename({"a": "b"})
        assert result is af

    def test_rename_updates_column_order(self):
        af = ActuarialFrame({"old_name": [1], "keep": [2]})
        af.rename({"old_name": "new_name"})
        assert "new_name" in af.get_column_order()
        assert "old_name" not in af.get_column_order()


class TestDrop:
    def test_drop_removes_columns(self, sample_af):
        result = sample_af.drop("status")
        collected = result.collect()
        assert "status" not in collected.columns
        assert "policy_id" in collected.columns

    def test_drop_multiple_columns(self, sample_af):
        result = sample_af.drop("status", "issue_age")
        collected = result.collect()
        assert "status" not in collected.columns
        assert "issue_age" not in collected.columns

    def test_drop_returns_self(self, sample_af):
        result = sample_af.drop("status")
        assert result is sample_af

    def test_drop_updates_column_order(self, sample_af):
        sample_af.drop("status")
        assert "status" not in sample_af.get_column_order()


class TestSort:
    def test_sort_orders_rows(self):
        af = ActuarialFrame({"id": ["C", "A", "B"], "val": [3, 1, 2]})
        af = af.sort("id")
        collected = af.collect()
        assert collected["id"].to_list() == ["A", "B", "C"]
        assert collected["val"].to_list() == [1, 2, 3]

    def test_sort_descending(self):
        af = ActuarialFrame({"age": [30, 55, 45]})
        af = af.sort("age", descending=True)
        assert af.collect()["age"].to_list() == [55, 45, 30]

    def test_sort_returns_self(self):
        af = ActuarialFrame({"a": [2, 1]})
        result = af.sort("a")
        assert result is af


class TestChaining:
    def test_rename_join_filter_chain(self):
        """The exact pattern from the example workflow — must work without collect/re-wrap."""
        expense_df = pl.DataFrame({
            "product_code": ["TERM", "WL"],
            "expense_pct": [0.05, 0.08],
        })

        af = ActuarialFrame({
            "policy_id": ["P001", "P002", "P003"],
            "Product Code": ["TERM", "WL", "TERM"],
            "Issue Age": [30, 45, 55],
            "status": ["IF", "LAPSED", "IF"],
        })

        af = (
            af.rename({"Product Code": "product_code", "Issue Age": "issue_age"})
              .join(expense_df, on="product_code")
              .filter(pl.col("status") == "IF")
              .drop("status")
              .sort("issue_age")
        )

        collected = af.collect()
        assert collected.height == 2
        assert "expense_pct" in collected.columns
        assert "status" not in collected.columns
        assert collected["issue_age"].to_list() == [30, 55]
