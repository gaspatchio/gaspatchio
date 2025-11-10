# ABOUTME: Integration test script to verify list broadcasting works in debug mode
# ABOUTME: Tests the real actuarial model pattern from basic_term model
# ruff: noqa: T201, PLR0911, PLR0912, PLR0915, ANN201, E501, SLF001, BLE001
# type: ignore[call-non-callable]

"""Integration test script for list broadcasting in debug mode."""

import sys

from gaspatchio_core import ActuarialFrame, when


def test_basic_term_pattern():
    """Test the pattern from basic_term model that was failing."""
    print("=" * 80)
    print("Integration Test: List Broadcasting in Debug Mode")
    print("=" * 80)

    # Create test data mimicking the basic_term model
    data = {
        "policy_id": [1, 2, 3],
        "policy_term": [2, 3, 5],  # 2, 3, 5 years
        "month": [
            [0, 12, 24, 36, 48, 60],
            [0, 12, 24, 36, 48, 60],
            [0, 12, 24, 36, 48, 60],
        ],
        "pols_if_raw": [
            [1000.0, 950.0, 900.0, 850.0, 800.0, 750.0],
            [2000.0, 1900.0, 1800.0, 1700.0, 1600.0, 1500.0],
            [3000.0, 2850.0, 2700.0, 2550.0, 2400.0, 2250.0],
        ],
    }

    print("\nTest Data:")
    print(f"  Policies: {len(data['policy_id'])}")
    print(f"  Policy terms: {data['policy_term']}")
    print()

    # Create ActuarialFrame in debug mode
    print("Step 1: Create ActuarialFrame in debug mode...")
    af = ActuarialFrame(data)
    af._tracing = True
    print("  ✓ Debug mode enabled")

    # Test 1: pols_maturity conditional (from line 112-114 of model_projection.py)
    print("\nStep 2: Apply pols_maturity conditional...")
    print(
        "  Expression: when(af.month == af.policy_term * 12).then(af.pols_if_raw).otherwise(0.0)"
    )

    try:
        af.pols_maturity = (
            when(af.month == af.policy_term * 12).then(af.pols_if_raw).otherwise(0.0)
        )
        print("  ✓ Conditional applied successfully (no NotImplementedError!)")
    except NotImplementedError as e:
        print(f"  ✗ FAILED: {e}")
        return False

    # Verify it was captured in computation graph
    print("\nStep 3: Check computation graph...")
    maturity_ops = [op for op in af._computation_graph if op.alias == "pols_maturity"]
    if maturity_ops:
        print(f"  ✓ Found {len(maturity_ops)} operation(s) for pols_maturity")
        op = maturity_ops[0]
        print(f"    - Expression: {op.expression}")
        print(f"    - Dependencies: {op.dependencies}")
    else:
        print("  ✗ FAILED: No operations captured in computation graph")
        return False

    # Test 2: pols_if conditional (from line 119-123 of model_projection.py)
    print("\nStep 4: Apply pols_if conditional...")
    print(
        "  Expression: when(af.month < af.policy_term * 12).then(af.pols_if_raw).otherwise(0.0)"
    )

    try:
        af.pols_if = (
            when(af.month < af.policy_term * 12).then(af.pols_if_raw).otherwise(0.0)
        )
        print("  ✓ Conditional applied successfully")
    except NotImplementedError as e:
        print(f"  ✗ FAILED: {e}")
        return False

    # Verify it was captured
    print("\nStep 5: Check computation graph again...")
    if_ops = [op for op in af._computation_graph if op.alias == "pols_if"]
    if if_ops:
        print(f"  ✓ Found {len(if_ops)} operation(s) for pols_if")
    else:
        print("  ✗ FAILED: No operations captured for pols_if")
        return False

    # Collect and verify results
    print("\nStep 6: Collect results...")
    try:
        result = af.collect()
        print("  ✓ Collect completed successfully")
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return False

    # Verify correctness
    print("\nStep 7: Verify correctness...")

    # Convert to lists for comparison
    result_maturity = result["pols_maturity"].to_list()
    result_if = result["pols_if"].to_list()

    # Policy 1: term=2 years (24 months), matures at month 24
    # pols_maturity should have 900.0 at index 2 (month 24), zeros elsewhere
    # pols_if should be [1000.0, 950.0, 0.0, 0.0, 0.0, 0.0]
    expected_maturity_1 = [0.0, 0.0, 900.0, 0.0, 0.0, 0.0]
    expected_if_1 = [1000.0, 950.0, 0.0, 0.0, 0.0, 0.0]

    if result_maturity[0] == expected_maturity_1:
        print("  ✓ Policy 1 pols_maturity correct")
    else:
        print("  ✗ Policy 1 pols_maturity incorrect")
        print(f"    Expected: {expected_maturity_1}")
        print(f"    Got: {result_maturity[0]}")
        return False

    if result_if[0] == expected_if_1:
        print("  ✓ Policy 1 pols_if correct")
    else:
        print("  ✗ Policy 1 pols_if incorrect")
        print(f"    Expected: {expected_if_1}")
        print(f"    Got: {result_if[0]}")
        return False

    # Policy 2: term=3 years (36 months), matures at month 36
    expected_maturity_2 = [0.0, 0.0, 0.0, 1700.0, 0.0, 0.0]
    expected_if_2 = [2000.0, 1900.0, 1800.0, 0.0, 0.0, 0.0]

    if result_maturity[1] == expected_maturity_2:
        print("  ✓ Policy 2 pols_maturity correct")
    else:
        print("  ✗ Policy 2 pols_maturity incorrect")
        print(f"    Expected: {expected_maturity_2}")
        print(f"    Got: {result_maturity[1]}")
        return False

    if result_if[1] == expected_if_2:
        print("  ✓ Policy 2 pols_if correct")
    else:
        print("  ✗ Policy 2 pols_if incorrect")
        print(f"    Expected: {expected_if_2}")
        print(f"    Got: {result_if[1]}")
        return False

    print("\n" + "=" * 80)
    print("SUCCESS: All tests passed!")
    print("=" * 80)
    print("\nSummary:")
    print("  • List broadcasting conditionals work in debug mode")
    print("  • Operations captured in computation graph")
    print("  • Results are correct")
    print("  • No NotImplementedError thrown")
    print()

    return True


def test_optimize_mode_comparison():
    """Test that optimize mode produces the same results."""
    print("=" * 80)
    print("Comparison Test: Debug vs Optimize Mode")
    print("=" * 80)

    data = {
        "policy_id": [1, 2],
        "policy_term": [2, 3],
        "month": [[0, 12, 24, 36], [0, 12, 24, 36]],
        "pols_if_raw": [
            [1000.0, 950.0, 900.0, 850.0],
            [2000.0, 1900.0, 1800.0, 1700.0],
        ],
    }

    # Run in debug mode
    print("\nRunning in debug mode...")
    af_debug = ActuarialFrame(data)
    af_debug._tracing = True
    af_debug.pols_maturity = (
        when(af_debug.month == af_debug.policy_term * 12)
        .then(af_debug.pols_if_raw)
        .otherwise(0.0)
    )
    af_debug.pols_if = (
        when(af_debug.month < af_debug.policy_term * 12)
        .then(af_debug.pols_if_raw)
        .otherwise(0.0)
    )
    result_debug = af_debug.collect()

    # Run in optimize mode
    print("Running in optimize mode...")
    af_opt = ActuarialFrame(data)
    af_opt._tracing = False
    af_opt.pols_maturity = (
        when(af_opt.month == af_opt.policy_term * 12)
        .then(af_opt.pols_if_raw)
        .otherwise(0.0)
    )
    af_opt.pols_if = (
        when(af_opt.month < af_opt.policy_term * 12)
        .then(af_opt.pols_if_raw)
        .otherwise(0.0)
    )
    result_opt = af_opt.collect()

    # Compare
    print("\nComparing results...")

    debug_maturity = result_debug["pols_maturity"].to_list()
    opt_maturity = result_opt["pols_maturity"].to_list()

    debug_if = result_debug["pols_if"].to_list()
    opt_if = result_opt["pols_if"].to_list()

    if debug_maturity == opt_maturity:
        print("  ✓ pols_maturity matches between modes")
    else:
        print("  ✗ pols_maturity differs between modes")
        print(f"    Debug: {debug_maturity}")
        print(f"    Optimize: {opt_maturity}")
        return False

    if debug_if == opt_if:
        print("  ✓ pols_if matches between modes")
    else:
        print("  ✗ pols_if differs between modes")
        print(f"    Debug: {debug_if}")
        print(f"    Optimize: {opt_if}")
        return False

    print("\n" + "=" * 80)
    print("SUCCESS: Debug and optimize modes produce identical results!")
    print("=" * 80)
    print()

    return True


if __name__ == "__main__":
    try:
        # Test 1: Basic functionality in debug mode
        success1 = test_basic_term_pattern()

        # Test 2: Compare debug vs optimize
        success2 = test_optimize_mode_comparison()

        if success1 and success2:
            print("\n" + "=" * 80)
            print("ALL INTEGRATION TESTS PASSED")
            print("=" * 80)
            sys.exit(0)
        else:
            print("\n" + "=" * 80)
            print("SOME TESTS FAILED")
            print("=" * 80)
            sys.exit(1)
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
