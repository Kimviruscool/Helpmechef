import requests

try:
    # Test valid URL (mock or real)
    response = requests.post(
        "http://127.0.0.1:8003/extract",
        data={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}...")
except Exception as e:
    print(f"Error: {e}")
