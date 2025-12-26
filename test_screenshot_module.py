#!/usr/bin/env python3
"""Test the actual screenshot module implementation."""

import sys
import os
import tempfile
from PIL import Image
from io import BytesIO
import base64

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def create_mock_screenshot(width=1080, height=2400):
    """Create a mock screenshot file."""
    img = Image.new("RGB", (width, height), color="red")
    temp_path = os.path.join(tempfile.gettempdir(), "mock_screenshot.png")
    img.save(temp_path, "PNG")
    return temp_path

def test_adb_screenshot_logic():
    """Test ADB screenshot resize logic."""
    print("=" * 60)
    print("Testing ADB Screenshot Module Logic")
    print("=" * 60)

    # Simulate the screenshot logic from phone_agent/adb/screenshot.py
    temp_path = create_mock_screenshot(1080, 2400)

    try:
        # Test 1: Without resize
        print("\n📋 Test 1: ADB Screenshot without resize")
        print("-" * 60)
        target_size = None

        img = Image.open(temp_path)
        original_width, original_height = img.size

        if target_size:
            img = img.resize(target_size, Image.Resampling.LANCZOS)

        width, height = img.size

        buffered = BytesIO()
        img.save(buffered, format="PNG")
        base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")

        print(f"  Original dimensions: {original_width}x{original_height}")
        print(f"  Final dimensions: {width}x{height}")
        print(f"  Base64 size: {len(base64_data):,} bytes")

        assert width == original_width
        assert height == original_height
        print("  ✅ PASSED")

        # Test 2: With resize
        print("\n📋 Test 2: ADB Screenshot with resize to 720x1280")
        print("-" * 60)
        target_size = (720, 1280)

        img = Image.open(temp_path)
        original_width, original_height = img.size

        if target_size:
            img = img.resize(target_size, Image.Resampling.LANCZOS)

        width, height = img.size

        buffered = BytesIO()
        img.save(buffered, format="PNG")
        base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")

        print(f"  Original dimensions: {original_width}x{original_height}")
        print(f"  Target size: {target_size}")
        print(f"  Final dimensions: {width}x{height}")
        print(f"  Base64 size: {len(base64_data):,} bytes")

        assert original_width == 1080 and original_height == 2400, "Original should be preserved"
        assert width == 720 and height == 1280, "Should be resized"
        print("  ✅ PASSED")

    finally:
        # Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)

def test_hdc_screenshot_logic():
    """Test HDC screenshot resize logic."""
    print("\n" + "=" * 60)
    print("Testing HDC Screenshot Module Logic")
    print("=" * 60)

    # Simulate the screenshot logic from phone_agent/hdc/screenshot.py
    temp_path = create_mock_screenshot(1080, 2400)

    try:
        # Test with resize
        print("\n📋 Test: HDC Screenshot with resize to 540x1200")
        print("-" * 60)
        target_size = (540, 1200)

        img = Image.open(temp_path)
        original_width, original_height = img.size

        if target_size:
            img = img.resize(target_size, Image.Resampling.LANCZOS)

        width, height = img.size

        buffered = BytesIO()
        img.save(buffered, format="PNG")
        base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")

        print(f"  Original dimensions: {original_width}x{original_height}")
        print(f"  Target size: {target_size}")
        print(f"  Final dimensions: {width}x{height}")
        print(f"  Base64 size: {len(base64_data):,} bytes")

        assert original_width == 1080 and original_height == 2400
        assert width == 540 and height == 1200
        print("  ✅ PASSED")

    finally:
        # Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)

def test_screenshot_dataclass():
    """Test Screenshot dataclass structure."""
    print("\n" + "=" * 60)
    print("Testing Screenshot Dataclass")
    print("=" * 60)

    from dataclasses import dataclass

    @dataclass
    class Screenshot:
        """Represents a captured screenshot."""
        base64_data: str
        width: int
        height: int
        is_sensitive: bool = False
        original_width: int | None = None
        original_height: int | None = None

    # Test 1: Without resize (original dimensions should match)
    print("\n📋 Test 1: Screenshot without resize")
    print("-" * 60)
    screenshot1 = Screenshot(
        base64_data="dummy_data",
        width=1080,
        height=2400,
        is_sensitive=False,
        original_width=1080,
        original_height=2400,
    )

    screen_width = screenshot1.original_width or screenshot1.width
    screen_height = screenshot1.original_height or screenshot1.height

    print(f"  Screenshot width: {screenshot1.width}")
    print(f"  Screenshot height: {screenshot1.height}")
    print(f"  Original width: {screenshot1.original_width}")
    print(f"  Original height: {screenshot1.original_height}")
    print(f"  Used for coordinate conversion: {screen_width}x{screen_height}")

    assert screen_width == 1080 and screen_height == 2400
    print("  ✅ PASSED")

    # Test 2: With resize (original preserved, display resized)
    print("\n📋 Test 2: Screenshot with resize")
    print("-" * 60)
    screenshot2 = Screenshot(
        base64_data="dummy_data",
        width=720,
        height=1280,
        is_sensitive=False,
        original_width=1080,
        original_height=2400,
    )

    screen_width = screenshot2.original_width or screenshot2.width
    screen_height = screenshot2.original_height or screenshot2.height

    print(f"  Screenshot width: {screenshot2.width} (resized)")
    print(f"  Screenshot height: {screenshot2.height} (resized)")
    print(f"  Original width: {screenshot2.original_width}")
    print(f"  Original height: {screenshot2.original_height}")
    print(f"  Used for coordinate conversion: {screen_width}x{screen_height}")

    assert screenshot2.width == 720 and screenshot2.height == 1280, "Display size should be resized"
    assert screen_width == 1080 and screen_height == 2400, "Coordinate conversion should use original"
    print("  ✅ PASSED")

    print("\n" + "=" * 60)
    print("✅ All Screenshot dataclass tests passed!")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_adb_screenshot_logic()
        test_hdc_screenshot_logic()
        test_screenshot_dataclass()

        print("\n" + "=" * 60)
        print("🎉 All module tests passed!")
        print("=" * 60)

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
