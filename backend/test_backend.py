"""
Test script for backend API
"""

import requests
import json
import uuid
import base64
from PIL import Image
import io

def create_test_image():
    """Create a simple test image and return base64 encoding"""
    # Create a simple 1080x1920 colored image
    img = Image.new('RGB', (1080, 1920), color='lightblue')

    # Convert to base64
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

    return img_base64

def test_health():
    """Test health check endpoint"""
    print("\n=== Testing Health Endpoint ===")
    response = requests.get("http://127.0.0.1:8020/api/health")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    print("✅ Health check passed!")

def test_conversation_basic():
    """Test conversation endpoint with basic request (no API call)"""
    print("\n=== Testing Conversation Endpoint (Basic) ===")

    conversation_id = str(uuid.uuid4())
    screenshot_base64 = create_test_image()

    payload = {
        "conversation_id": conversation_id,
        "screenshot": screenshot_base64,
        "current_package_name": "com.android.launcher",
        "prompt": "测试消息,不需要实际调用API"
    }

    print(f"Conversation ID: {conversation_id}")
    print(f"Screenshot size: {len(screenshot_base64)} chars")
    print(f"Package name: {payload['current_package_name']}")
    print(f"Prompt: {payload['prompt']}")

    # Note: This will fail because we don't have API key set
    # But it will test the endpoint structure
    print("\nNote: This test will fail without OPENAI_API_KEY, but validates endpoint structure")

def test_conversation_structure():
    """Test conversation endpoint structure without API key"""
    print("\n=== Testing Conversation Endpoint Structure ===")

    conversation_id = str(uuid.uuid4())

    # Test with missing conversation_id
    print("\n1. Testing missing conversation_id...")
    response = requests.post(
        "http://127.0.0.1:8020/api/conversation",
        json={}
    )
    print(f"   Status Code: {response.status_code}")
    print(f"   Response: {response.json()}")
    assert response.status_code == 400
    print("   ✅ Correctly rejects missing conversation_id")

    # Test with valid structure (will fail at API key check)
    print("\n2. Testing with valid structure (expect API key error)...")
    screenshot_base64 = create_test_image()
    payload = {
        "conversation_id": conversation_id,
        "screenshot": screenshot_base64,
        "current_package_name": "com.xingin.xhs",
        "prompt": "打开小红书"
    }

    response = requests.post(
        "http://127.0.0.1:8020/api/conversation",
        json=payload
    )
    print(f"   Status Code: {response.status_code}")
    print(f"   Response: {response.json()}")
    # Should get 500 error due to missing API key
    assert response.status_code == 500
    assert "OPENAI_API_KEY" in response.json().get("error", "")
    print("   ✅ Correctly reports API key error")

def test_delete_conversation():
    """Test delete conversation endpoint"""
    print("\n=== Testing Delete Conversation Endpoint ===")

    conversation_id = str(uuid.uuid4())

    response = requests.delete(f"http://127.0.0.1:8020/api/conversation/{conversation_id}")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    print("✅ Delete conversation passed!")

def main():
    """Run all tests"""
    print("=" * 60)
    print("Backend API Test Suite")
    print("=" * 60)

    try:
        test_health()
        test_conversation_structure()
        test_delete_conversation()

        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        print("\nNote: Full conversation tests require OPENAI_API_KEY to be set")
        print("Set it with: export OPENAI_API_KEY='your-key-here'")

    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
