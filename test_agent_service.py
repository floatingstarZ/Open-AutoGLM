#!/usr/bin/env python3
"""Test script for AgentService and K-image filtering."""

import json
from phone_agent.agent_service import AgentService, InferenceConfig
from phone_agent.model import ModelConfig


def test_filter_k_images():
    """Test K-image filtering algorithm."""
    print("Testing K-image filtering algorithm...")
    print("=" * 60)

    # Create a mock service (we only need the filtering method)
    config = ModelConfig()
    inference_config = InferenceConfig(k_images=2)
    service = AgentService(config, inference_config)

    # Create test messages with 3 images
    messages = [
        {"role": "system", "content": "You are a phone agent"},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,IMAGE1"}},
                {"type": "text", "text": "Open WeChat"},
            ],
        },
        {"role": "assistant", "content": "<think>Thinking...</think><answer>do(...)</answer>"},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,IMAGE2"}},
                {"type": "text", "text": "Screen info..."},
            ],
        },
        {"role": "assistant", "content": "<think>Thinking...</think><answer>do(...)</answer>"},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,IMAGE3"}},
                {"type": "text", "text": "Screen info..."},
            ],
        },
    ]

    print(f"\nOriginal messages: {len(messages)} messages")
    print(f"Images in messages: 3 (IMAGE1, IMAGE2, IMAGE3)")
    print(f"K value: {inference_config.k_images}")

    # Filter to K=2 most recent images
    filtered = service._filter_k_images(messages, k=2)

    print(f"\nFiltered messages: {len(filtered)} messages")

    # Count images in filtered messages
    image_count = 0
    images_found = []
    for i, msg in enumerate(filtered):
        if msg.get("role") == "user":
            content = msg.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if item.get("type") == "image_url":
                        image_count += 1
                        url = item["image_url"]["url"]
                        # Extract IMAGE number
                        if "IMAGE" in url:
                            img_id = url.split("IMAGE")[1].split('"')[0]
                            images_found.append(f"IMAGE{img_id}")

    print(f"Images in filtered messages: {image_count}")
    print(f"Images found: {images_found}")

    # Verify
    print("\n" + "=" * 60)
    if image_count == 2 and images_found == ["IMAGE2", "IMAGE3"]:
        print("✅ TEST PASSED: K-image filtering works correctly!")
        print("   - Kept IMAGE2 and IMAGE3 (most recent 2 images)")
        print("   - Removed IMAGE1 (oldest image)")
        return True
    else:
        print("❌ TEST FAILED: K-image filtering did not work as expected")
        print(f"   Expected: 2 images [IMAGE2, IMAGE3]")
        print(f"   Got: {image_count} images {images_found}")
        return False


def test_filter_k_images_edge_cases():
    """Test edge cases for K-image filtering."""
    print("\n\nTesting edge cases...")
    print("=" * 60)

    config = ModelConfig()
    service = AgentService(config, InferenceConfig(k_images=0))

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,IMG"}},
                {"type": "text", "text": "Hello"},
            ],
        },
    ]

    # Test k=0 (remove all images)
    print("\nTest 1: k=0 (remove all images)")
    filtered = service._filter_k_images(messages, k=0)
    has_image = any(
        item.get("type") == "image_url"
        for msg in filtered
        if msg.get("role") == "user"
        for item in msg.get("content", [])
    )
    if not has_image:
        print("✅ PASSED: All images removed")
    else:
        print("❌ FAILED: Images still present")

    # Test k=-1 (keep all images)
    print("\nTest 2: k=-1 (keep all images)")
    filtered = service._filter_k_images(messages, k=-1)
    has_image = any(
        item.get("type") == "image_url"
        for msg in filtered
        if msg.get("role") == "user"
        for item in msg.get("content", [])
    )
    if has_image:
        print("✅ PASSED: All images kept")
    else:
        print("❌ FAILED: Images were removed")

    # Test k > total images
    print("\nTest 3: k=10 (more than available images)")
    filtered = service._filter_k_images(messages, k=10)
    image_count = sum(
        1
        for msg in filtered
        if msg.get("role") == "user"
        for item in msg.get("content", [])
        if item.get("type") == "image_url"
    )
    if image_count == 1:
        print("✅ PASSED: Kept all available images (1)")
    else:
        print(f"❌ FAILED: Expected 1 image, got {image_count}")

    # Test text preservation
    print("\nTest 4: Text content preservation")
    filtered = service._filter_k_images(messages, k=0)
    text_preserved = any(
        item.get("type") == "text"
        for msg in filtered
        if msg.get("role") == "user"
        for item in msg.get("content", [])
    )
    if text_preserved:
        print("✅ PASSED: Text content preserved even when images removed")
    else:
        print("❌ FAILED: Text content was removed")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("AgentService Test Suite")
    print("=" * 60)

    # Run basic test
    success = test_filter_k_images()

    # Run edge case tests
    test_filter_k_images_edge_cases()

    print("\n" + "=" * 60)
    if success:
        print("✅ All core tests passed!")
    else:
        print("❌ Some tests failed")
    print("=" * 60)


if __name__ == "__main__":
    main()
