import requests
import re
import json
import time

url = "https://www.youtube.com/watch?v=necxO0Qk9y0"
print(f"Fetching {url}...")
start = time.time()
try:
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    print(f"Fetch took {time.time() - start:.2f}s. Status: {response.status_code}")
    
    html_content = response.text
    print(f"HTML length: {len(html_content)}")
    
    print("Searching for ytInitialPlayerResponse...")
    start = time.time()
    match = re.search(r'var ytInitialPlayerResponse\s*=\s*(\{.*?\});', html_content)
    if not match:
        print("Regex 1 failed. Trying regex 2...")
        match = re.search(r'ytInitialPlayerResponse\s*=\s*(\{.*?\});', html_content)
        
    print(f"Regex took {time.time() - start:.2f}s")
    
    if match:
        print("MATCH FOUND!")
        data = json.loads(match.group(1))
        
        # Save JSON for inspection
        with open("debug_player.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        print("Keys:", list(data.keys()))
        if "playabilityStatus" in data:
            print("Playability:", data["playabilityStatus"].get("status"))
            
        captions = data.get("captions")
        if captions:
            print("Captions found!")
        else:
            print("No captions in data. usage: data.get('captions') is None")
    else:
        print("NO MATCH found.")
        with open("debug_html_standalone.txt", "w", encoding="utf-8") as f:
            f.write(html_content)
            
except Exception as e:
    print(f"Error: {e}")
