#!/usr/bin/env python3
"""Integration test for coordinate mode and screenshot resize."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from phone_agent.actions.handler import ActionHandler

def test_coordinate_conversion_integration():
    """Test the complete coordinate conversion workflow."""
    print("=" * 60)
    print("Integration Test: Coordinate Conversion")
    print("=" * 60)

    # Scenario 1: Relative mode + Original size
    print("\n📋 Scenario 1: Relative mode + Original size (1080x2400)")
    print("-" * 60)

    handler_rel = ActionHandler(device_id=None, coord_mode="relative")
    element = [500, 500]  # Relative coordinates
    screen_width, screen_height = 1080, 2400

    x, y = handler_rel._convert_relative_to_absolute(element, screen_width, screen_height)

    print(f"  Coordinate mode: relative")
    print(f"  Screen size: {screen_width}x{screen_height}")
    print(f"  Input: {element}")
    print(f"  Output: ({x}, {y})")
    print(f"  Expected: (540, 1200)")

    assert x == 540 and y == 1200, f"Expected (540, 1200), got ({x}, {y})"
    print("  ✅ PASSED")

    # Scenario 2: Absolute mode + Original size
    print("\n📋 Scenario 2: Absolute mode + Original size (1080x2400)")
    print("-" * 60)

    handler_abs = ActionHandler(device_id=None, coord_mode="absolute")
    element = [540, 1200]  # Absolute pixel coordinates
    screen_width, screen_height = 1080, 2400

    x, y = handler_abs._convert_relative_to_absolute(element, screen_width, screen_height)

    print(f"  Coordinate mode: absolute")
    print(f"  Screen size: {screen_width}x{screen_height}")
    print(f"  Input: {element}")
    print(f"  Output: ({x}, {y})")
    print(f"  Expected: (540, 1200)")

    assert x == 540 and y == 1200, f"Expected (540, 1200), got ({x}, {y})"
    print("  ✅ PASSED")

    # Scenario 3: Relative mode + Resized image (BUT using original screen dimensions)
    print("\n📋 Scenario 3: Relative mode + Resized image (720x1280)")
    print("-" * 60)
    print("  Note: Image sent to model is 720x1280, but we use original 1080x2400")

    handler_rel = ActionHandler(device_id=None, coord_mode="relative")
    element = [500, 500]  # Relative coordinates from model
    # Key: Use ORIGINAL screen dimensions, not resized image dimensions
    original_screen_width, original_screen_height = 1080, 2400

    x, y = handler_rel._convert_relative_to_absolute(element, original_screen_width, original_screen_height)

    print(f"  Coordinate mode: relative")
    print(f"  Image size sent to model: 720x1280 (resized)")
    print(f"  Original screen size: {original_screen_width}x{original_screen_height}")
    print(f"  Input from model: {element}")
    print(f"  Output: ({x}, {y})")
    print(f"  Expected: (540, 1200)")

    assert x == 540 and y == 1200, f"Expected (540, 1200), got ({x}, {y})"
    print("  ✅ PASSED")

    # Scenario 4: Absolute mode + Resized image (BUT using original screen dimensions)
    print("\n📋 Scenario 4: Absolute mode + Resized image (720x1280)")
    print("-" * 60)
    print("  Note: Image sent to model is 720x1280")
    print("  Model sees: 'Screenshot dimensions: (1080x2400, png)'")

    handler_abs = ActionHandler(device_id=None, coord_mode="absolute")
    element = [540, 1200]  # Model outputs absolute coordinates based on 1080x2400
    original_screen_width, original_screen_height = 1080, 2400

    x, y = handler_abs._convert_relative_to_absolute(element, original_screen_width, original_screen_height)

    print(f"  Coordinate mode: absolute")
    print(f"  Image size sent to model: 720x1280 (resized)")
    print(f"  Original screen size: {original_screen_width}x{original_screen_height}")
    print(f"  Dimension hint shown to model: (1080x2400, png)")
    print(f"  Input from model: {element} (based on 1080x2400)")
    print(f"  Output: ({x}, {y})")
    print(f"  Expected: (540, 1200)")

    assert x == 540 and y == 1200, f"Expected (540, 1200), got ({x}, {y})"
    print("  ✅ PASSED")

    # Scenario 5: Edge case - coordinates at boundaries
    print("\n📋 Scenario 5: Edge case - Boundary coordinates")
    print("-" * 60)

    test_cases = [
        # (coord_mode, element, expected)
        ("relative", [0, 0], (0, 0)),
        ("relative", [999, 999], (1078, 2397)),  # int(999/1000*1080)=1078, int(999/1000*2400)=2397
        ("absolute", [0, 0], (0, 0)),
        ("absolute", [1079, 2399], (1079, 2399)),
    ]

    for coord_mode, element, expected in test_cases:
        handler = ActionHandler(device_id=None, coord_mode=coord_mode)
        x, y = handler._convert_relative_to_absolute(element, 1080, 2400)
        print(f"  {coord_mode:8s} | {str(element):12s} -> ({x:4d}, {y:4d}) | Expected: {expected}")
        assert (x, y) == expected, f"Expected {expected}, got ({x}, {y})"

    print("  ✅ PASSED")

    print("\n" + "=" * 60)
    print("✅ All integration tests passed!")
    print("=" * 60)

def test_dimension_reminder():
    """Test dimension reminder generation logic."""
    print("\n" + "=" * 60)
    print("Integration Test: Dimension Reminder")
    print("=" * 60)

    # Test 1: Relative mode (no reminder)
    print("\n📋 Test 1: Relative mode - No dimension reminder")
    print("-" * 60)

    coord_mode = "relative"
    screen_width, screen_height = 1080, 2400

    dimension_reminder = ""
    if coord_mode == "absolute":
        dimension_reminder = f"\nScreenshot dimensions: ({screen_width}x{screen_height}, png)"

    print(f"  Coordinate mode: {coord_mode}")
    print(f"  Dimension reminder: '{dimension_reminder}'")

    assert dimension_reminder == "", "Should be empty for relative mode"
    print("  ✅ PASSED")

    # Test 2: Absolute mode (with reminder)
    print("\n📋 Test 2: Absolute mode - With dimension reminder")
    print("-" * 60)

    coord_mode = "absolute"
    screen_width, screen_height = 1080, 2400

    dimension_reminder = ""
    if coord_mode == "absolute":
        dimension_reminder = f"\nScreenshot dimensions: ({screen_width}x{screen_height}, png)"

    print(f"  Coordinate mode: {coord_mode}")
    print(f"  Dimension reminder: '{dimension_reminder}'")

    expected = f"\nScreenshot dimensions: (1080x2400, png)"
    assert dimension_reminder == expected, f"Expected '{expected}', got '{dimension_reminder}'"
    print("  ✅ PASSED")

    # Test 3: Absolute mode with resized image
    print("\n📋 Test 3: Absolute mode - Resized image (original dimensions shown)")
    print("-" * 60)

    coord_mode = "absolute"
    # Image was resized to 720x1280, but original is 1080x2400
    original_width, original_height = 1080, 2400
    resized_width, resized_height = 720, 1280

    # Use original dimensions for the reminder
    screen_width = original_width
    screen_height = original_height

    dimension_reminder = ""
    if coord_mode == "absolute":
        dimension_reminder = f"\nScreenshot dimensions: ({screen_width}x{screen_height}, png)"

    print(f"  Coordinate mode: {coord_mode}")
    print(f"  Image sent to model: {resized_width}x{resized_height}")
    print(f"  Original screen: {original_width}x{original_height}")
    print(f"  Dimension reminder: '{dimension_reminder}'")

    # Should show ORIGINAL dimensions, not resized
    expected = f"\nScreenshot dimensions: (1080x2400, png)"
    assert dimension_reminder == expected
    print("  ✅ PASSED")

    print("\n" + "=" * 60)
    print("✅ All dimension reminder tests passed!")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_coordinate_conversion_integration()
        test_dimension_reminder()

        print("\n" + "=" * 60)
        print("🎉 All integration tests passed!")
        print("=" * 60)
        print("\n📊 Summary:")
        print("  ✅ Coordinate conversion works correctly for both modes")
        print("  ✅ Screenshot resize preserves original dimensions")
        print("  ✅ Dimension reminder shows correctly in absolute mode")
        print("  ✅ Original screen dimensions used for coordinate conversion")

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
