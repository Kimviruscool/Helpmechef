import requests
import json

try:
    # Test with a known cooking video (Baek Jong-won Kimchi Jjigae)
    # Using a real video ID to test transcript fetching too
    video_id = "dQw4w9WgXcQ" # Rick Roll (Known to work)
    print(f"Sending request for video {video_id}...")
    response = requests.post(
        "http://127.0.0.1:8003/extract",
        data={"url": f"https://www.youtube.com/watch?v={video_id}"},
        timeout=60
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    print("Title:", data.get("title"))
    print("Description Start:", data.get("description")[:50])
    
    if "API 오류" in data.get("title", ""):
        print("\n[FAILURE] Still returning Mock Data due to API Error.")
    elif "[데모 모드]" in data.get("description", ""):
         print("\n[FAILURE] Still returning Mock Data due to missing Key.")
    else:
        print("\n[SUCCESS] Seems to be real data!")
        print(json.dumps(data, indent=2, ensure_ascii=False))

except Exception as e:
    print(f"Error: {e}")
