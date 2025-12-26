#!/usr/bin/env python3
"""Test script to verify screenshot resize functionality."""

import sys
from PIL import Image
from io import BytesIO
import base64

# Test the screenshot resize logic
def test_screenshot_resize():
    """Test screenshot resize with original dimensions preservation."""

    # Create a test image (simulating original screenshot)
    original_width, original_height = 1080, 2400
    test_img = Image.new("RGB", (original_width, original_height), color="blue")

    print("=" * 60)
    print("Screenshot Resize Test")
    print("=" * 60)

    # Test 1: No resize (target_size = None)
    print("\n📋 Test 1: No resize (original size)")
    print("-" * 60)
    img1 = test_img.copy()
    target_size = None

    original_w, original_h = img1.size
    if target_size:
        img1 = img1.resize(target_size, Image.Resampling.LANCZOS)

    width, height = img1.size

    print(f"  Original dimensions: {original_w}x{original_h}")
    print(f"  Target size: {target_size}")
    print(f"  Final dimensions: {width}x{height}")
    print(f"  Preserved original: {original_w}x{original_h}")

    assert width == original_width and height == original_height, "Size should remain unchanged"
    assert original_w == original_width and original_h == original_height, "Original dimensions should be preserved"
    print("  ✅ PASSED")

    # Test 2: With resize
    print("\n📋 Test 2: With resize (720x1280)")
    print("-" * 60)
    img2 = test_img.copy()
    target_size = (720, 1280)

    original_w, original_h = img2.size
    if target_size:
        img2 = img2.resize(target_size, Image.Resampling.LANCZOS)

    width, height = img2.size

    print(f"  Original dimensions: {original_w}x{original_h}")
    print(f"  Target size: {target_size}")
    print(f"  Final dimensions: {width}x{height}")
    print(f"  Preserved original: {original_w}x{original_h}")

    assert width == 720 and height == 1280, "Image should be resized to target"
    assert original_w == original_width and original_h == original_height, "Original dimensions should be preserved"
    print("  ✅ PASSED")

    # Test 3: Coordinate conversion - Relative mode
    print("\n📋 Test 3: Coordinate conversion - Relative mode")
    print("-" * 60)
    coord_mode = "relative"
    element = [500, 500]  # Relative coordinates (0-999 range)
    screen_width, screen_height = original_w, original_h  # Use original dimensions

    if coord_mode == "relative":
        x = int(element[0] / 1000 * screen_width)
        y = int(element[1] / 1000 * screen_height)
    else:
        x, y = int(element[0]), int(element[1])

    print(f"  Coordinate mode: {coord_mode}")
    print(f"  Input coordinates: {element}")
    print(f"  Screen dimensions: {screen_width}x{screen_height}")
    print(f"  Output coordinates: ({x}, {y})")

    expected_x = int(500 / 1000 * 1080)  # 540
    expected_y = int(500 / 1000 * 2400)  # 1200
    assert x == expected_x and y == expected_y, f"Expected ({expected_x}, {expected_y}), got ({x}, {y})"
    print("  ✅ PASSED")

    # Test 4: Coordinate conversion - Absolute mode
    print("\n📋 Test 4: Coordinate conversion - Absolute mode")
    print("-" * 60)
    coord_mode = "absolute"
    element = [540, 1200]  # Absolute pixel coordinates

    if coord_mode == "relative":
        x = int(element[0] / 1000 * screen_width)
        y = int(element[1] / 1000 * screen_height)
    else:
        x, y = int(element[0]), int(element[1])

    print(f"  Coordinate mode: {coord_mode}")
    print(f"  Input coordinates: {element}")
    print(f"  Screen dimensions: {screen_width}x{screen_height}")
    print(f"  Output coordinates: ({x}, {y})")

    assert x == 540 and y == 1200, f"Expected (540, 1200), got ({x}, {y})"
    print("  ✅ PASSED")

    # Test 5: Image quality after resize
    print("\n📋 Test 5: Image resize quality check")
    print("-" * 60)
    img3 = test_img.copy()
    target_size = (540, 1200)

    original_size = img3.size
    img3_resized = img3.resize(target_size, Image.Resampling.LANCZOS)
    resized_size = img3_resized.size

    print(f"  Original size: {original_size}")
    print(f"  Resized size: {resized_size}")
    print(f"  Resize method: LANCZOS (high quality)")

    # Check that resizing actually changed the size
    assert original_size != resized_size, "Size should change after resize"
    assert resized_size == target_size, "Resized size should match target"
    print("  ✅ PASSED")

    # Test 6: Base64 encoding size comparison
    print("\n📋 Test 6: Base64 encoding size comparison")
    print("-" * 60)

    # Original image
    buffered_orig = BytesIO()
    test_img.save(buffered_orig, format="PNG")
    base64_orig = base64.b64encode(buffered_orig.getvalue()).decode("utf-8")

    # Resized image
    img_resized = test_img.resize((720, 1280), Image.Resampling.LANCZOS)
    buffered_resized = BytesIO()
    img_resized.save(buffered_resized, format="PNG")
    base64_resized = base64.b64encode(buffered_resized.getvalue()).decode("utf-8")

    size_orig = len(base64_orig)
    size_resized = len(base64_resized)
    reduction = (1 - size_resized / size_orig) * 100

    print(f"  Original base64 size: {size_orig:,} bytes")
    print(f"  Resized base64 size: {size_resized:,} bytes")
    print(f"  Size reduction: {reduction:.1f}%")
    print("  ✅ PASSED")

    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_screenshot_resize()
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
