def test_assumption_import():
    """Test that importing from gaspatchio_core.assumptions works correctly"""
    from gaspatchio_core.assumptions import table_registry

    # Verify that the imported module has the expected functionality
    assert hasattr(table_registry, "KeySpec")
    assert hasattr(table_registry, "TableRegistry")
    assert hasattr(table_registry, "py_get_registry")
    print("Import successful! table_registry has expected attributes.")


if __name__ == "__main__":
    test_assumption_import()
