#!/usr/bin/env python3
"""
Debug tool for current app detection.

This script helps diagnose issues with get_current_app() by showing
the raw output from dumpsys/hidumper and the parsed result.
"""

import subprocess
import sys
import re


def debug_adb_current_app(device_id=None):
    """Debug ADB current app detection."""
    print("=" * 60)
    print("Debugging ADB Current App Detection")
    print("=" * 60)

    # Prepare ADB command
    adb_prefix = ["adb"]
    if device_id:
        adb_prefix = ["adb", "-s", device_id]

    # Run dumpsys window
    print("\n[1] Running: adb shell dumpsys window...")
    result = subprocess.run(
        adb_prefix + ["shell", "dumpsys", "window"],
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    if result.returncode != 0:
        print(f"Error: Command failed with code {result.returncode}")
        print(f"stderr: {result.stderr}")
        return

    output = result.stdout

    # Find relevant lines
    print("\n[2] Looking for mCurrentFocus or mFocusedApp...")
    focus_lines = []
    for line in output.split("\n"):
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            focus_lines.append(line.strip())

    if not focus_lines:
        print("❌ No focus information found!")
        print("\nShowing first 50 lines of output:")
        print("-" * 60)
        for i, line in enumerate(output.split("\n")[:50]):
            print(f"{i+1:3d}: {line}")
        return

    print(f"✅ Found {len(focus_lines)} focus line(s):")
    print("-" * 60)
    for line in focus_lines:
        print(line)
    print("-" * 60)

    # Try to extract package name
    print("\n[3] Extracting package name...")
    for line in focus_lines:
        match = re.search(r'([a-z][a-z0-9_]*(\.[a-z0-9_]+)+)', line)
        if match:
            package_name = match.group(1)
            # Clean up if it's an activity name
            if '/' in package_name:
                package_name = package_name.split('/')[0]
            print(f"✅ Extracted package: {package_name}")
            return package_name

    print("❌ Could not extract package name from focus lines")
    return None


def debug_hdc_current_app(device_id=None):
    """Debug HDC current app detection."""
    print("=" * 60)
    print("Debugging HDC Current App Detection")
    print("=" * 60)

    # Prepare HDC command
    hdc_prefix = ["hdc"]
    if device_id:
        hdc_prefix = ["hdc", "-t", device_id]

    # Run hidumper
    print("\n[1] Running: hdc shell hidumper -s WindowManagerService...")
    result = subprocess.run(
        hdc_prefix + ["shell", "hidumper", "-s", "WindowManagerService", "-a", "-a"],
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    if result.returncode != 0:
        print(f"Error: Command failed with code {result.returncode}")
        print(f"stderr: {result.stderr}")
        return

    output = result.stdout

    # Find relevant lines
    print("\n[2] Looking for 'focused' or 'current'...")
    focus_lines = []
    for line in output.split("\n"):
        if "focused" in line.lower() or "current" in line.lower():
            focus_lines.append(line.strip())

    if not focus_lines:
        print("❌ No focus information found!")
        print("\nShowing first 50 lines of output:")
        print("-" * 60)
        for i, line in enumerate(output.split("\n")[:50]):
            print(f"{i+1:3d}: {line}")
        return

    print(f"✅ Found {len(focus_lines)} relevant line(s):")
    print("-" * 60)
    for line in focus_lines[:10]:  # Show first 10
        print(line)
    print("-" * 60)

    # Try to extract bundle name
    print("\n[3] Extracting bundle name...")
    for line in focus_lines:
        match = re.search(r'([a-z][a-z0-9_]*(\.[a-z0-9_]+)+)', line)
        if match:
            bundle_name = match.group(1)
            print(f"✅ Extracted bundle: {bundle_name}")
            return bundle_name

    print("❌ Could not extract bundle name from focus lines")
    return None


def main():
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
        print("Usage:")
        print("  python debug_current_app.py [adb|hdc] [device_id]")
        print("\nExamples:")
        print("  python debug_current_app.py")
        print("  python debug_current_app.py adb")
        print("  python debug_current_app.py hdc")
        print("  python debug_current_app.py adb emulator-5554")
        return

    # Determine device type
    device_type = "adb"  # default
    device_id = None

    if len(sys.argv) > 1:
        device_type = sys.argv[1].lower()

    if len(sys.argv) > 2:
        device_id = sys.argv[2]

    # Run appropriate debug function
    if device_type == "hdc":
        package = debug_hdc_current_app(device_id)
    else:
        package = debug_adb_current_app(device_id)

    print("\n" + "=" * 60)
    if package:
        print(f"✅ Final result: {package}")
    else:
        print("❌ Could not detect current app")
    print("=" * 60)


if __name__ == "__main__":
    main()
