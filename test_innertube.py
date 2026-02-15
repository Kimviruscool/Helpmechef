import requests
import re
import json

video_id = "necxO0Qk9y0"
url = f"https://www.youtube.com/watch?v={video_id}"
headers = {"User-Agent": "Mozilla/5.0"}

print("Fetching page to get API Key...")
response = requests.get(url, headers=headers)
html = response.text

# 1. Extract API Key
key_match = re.search(r'"INNERTUBE_API_KEY":"(.*?)"', html)
if not key_match:
    print("Could not find INNERTUBE_API_KEY")
    exit()
    
api_key = key_match.group(1)
print(f"API Key: {api_key}")

# 2. Extract Client Version
context_match = re.search(r'"INNERTUBE_CONTEXT_CLIENT_VERSION":"(.*?)"', html)
client_version = context_match.group(1) if context_match else "2.20230628.00.00"
print(f"Client Version: {client_version}")

# 3. Call Innertube API
api_url = f"https://www.youtube.com/youtubei/v1/player?key={api_key}"
payload = {
    "context": {
        "client": {
            "hl": "ko",
            "gl": "KR",
            "clientName": "WEB",
            "clientVersion": client_version
        }
    },
    "videoId": video_id
}

print("Calling Innertube API...")
r = requests.post(api_url, json=payload, headers=headers)
print(f"Status: {r.status_code}")
data = r.json()

if "streamingData" in data:
    print("Streaming data found (Video Playable)")
    
playability = data.get("playabilityStatus", {})
print(f"Playability: {playability.get('status')}")

captions = data.get("captions")
if captions:
    print("Captions Found!")
    print(json.dumps(captions, indent=2, ensure_ascii=False)[:500])
else:
    print("No captions in API response.")
