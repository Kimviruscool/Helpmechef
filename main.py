from fastapi import FastAPI, Request, Form, HTTPException, Body
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import google.generativeai as genai
from dotenv import load_dotenv
from pydantic import BaseModel
import uuid
import requests
import os
import json
import re
import html
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from yt_dlp import YoutubeDL

# Load environment variables
load_dotenv()

app = FastAPI()

# Data Models
class Recipe(BaseModel):
    title: str
    description: Optional[str] = ""
    ingredients: List[str]
    steps: List[str]
    tips: Optional[List[str]] = []
    video_id: str
    thumbnail: Optional[str] = ""

class Bookmark(Recipe):
    id: str

# Bookmarks Storage
BOOKMARKS_FILE = "bookmarks.json"

def load_bookmarks() -> List[Dict]:
    if not os.path.exists(BOOKMARKS_FILE):
        return []
    try:
        with open(BOOKMARKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_bookmarks(bookmarks: List[Dict]):
    with open(BOOKMARKS_FILE, "w", encoding="utf-8") as f:
        json.dump(bookmarks, f, ensure_ascii=False, indent=2)

# Mount static files if the directory exists
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
# Keep serving templates
templates = Jinja2Templates(directory="templates")

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("gemini_api_key")
if GEMINI_API_KEY:
    GEMINI_API_KEY = GEMINI_API_KEY.strip() # Remove any leading/trailing whitespace
    print(f"DEBUG: Gemini API Key loaded (Length: {len(GEMINI_API_KEY)})")
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("DEBUG: Gemini API Key NOT found in environment variables.")

def get_video_id(url: str) -> Optional[str]:
    """Extracts video ID from YouTube URL (including Shorts)."""
    # Supports:
    # - youtube.com/watch?v=VIDEO_ID
    # - youtube.com/shorts/VIDEO_ID
    # - youtu.be/VIDEO_ID
    pattern = r"(?:v=|\/shorts\/|\/embed\/|\.be\/|\/v\/|\/e\/|watch\?v=|&v=)([^#&?\/]{11})"
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return None

def get_video_title(video_id: str) -> str:
    """Scrapes the video title from the YouTube page."""
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code == 200:
            match = re.search(r'<title>(.*?)</title>', response.text)
            if match:
                title = match.group(1).replace(" - YouTube", "")
                return title
    except Exception:
        pass
    return "YouTube Video"

def get_transcript(video_id: str) -> str:
    """Fetches transcript using YouTubeTranscriptApi first, then yt-dlp as fallback."""
    print(f"DEBUG: Fetching transcript for {video_id}...")
    
    # 1. Try YouTubeTranscriptApi (Best for captions)
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
        full_text = " ".join([entry['text'] for entry in transcript_list])
        print("DEBUG: Successfully fetched via YouTubeTranscriptApi")
        return full_text
    except Exception as e:
        print(f"DEBUG: YouTubeTranscriptApi failed: {str(e)}")
        
    # 2. Fallback: yt-dlp (Good for auto-generated heavily heavily obfuscated ones sometimes)
    try:
        print("DEBUG: Attempting fallback with yt-dlp...")
        url = f"https://www.youtube.com/watch?v={video_id}"
        ydl_opts = {
            'writesubtitles': True,
            'writeautomaticsub': True,
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except Exception as e:
                return f"ERROR: yt-dlp failed to extract info: {str(e)}"
                
        subtitles = info.get('subtitles', {})
        automatic_captions = info.get('automatic_captions', {})
        
        # Priority: Korean (Manual) -> English (Manual) -> Korean (Auto) -> English (Auto)
        selected_sub = None
        for lang in ['ko', 'en']:
            if lang in subtitles:
                selected_sub = subtitles[lang]
                break
        
        if not selected_sub:
             for lang in ['ko', 'en']:
                if lang in automatic_captions:
                    selected_sub = automatic_captions[lang]
                    break
                    
        # Fallback to any available
        if not selected_sub:
            if subtitles:
                selected_sub = next(iter(subtitles.values()))
            elif automatic_captions:
                selected_sub = next(iter(automatic_captions.values()))
                
        if not selected_sub:
            return "ERROR: No subtitles found for this video."

        # Fetch the subtitle content
        sub_url = None
        # Prefer 'srv1' (XML) or 'json3' or 'vtt'
        for fmt in selected_sub:
            if fmt.get('ext') in ['srv1', 'xml']:
                sub_url = fmt['url']
                break
        
        if not sub_url:
             sub_url = selected_sub[-1]['url'] # Fallback to last one

        response = requests.get(sub_url)
        if response.status_code != 200:
            return "ERROR: Failed to download subtitle content."
            
        content = response.text
        
        # Simple XML parsing if it looks like XML
        if content.strip().startswith("<?xml") or "<text" in content:
            try:
                root = ET.fromstring(content)
                lines = []
                for child in root.findall(".//text"):
                    if child.text:
                        lines.append(html.unescape(child.text))
                return " ".join(lines)
            except:
                pass # Fallback to raw text if parsing fails
        
        return content

    except Exception as e:
        error_msg = f"ERROR: Extraction failed: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return error_msg

def mock_recipe(video_id: str) -> Dict:
    """Returns a mock recipe for demonstration purposes."""
    return {
        "title": "백종원의 김치찌개 (예시 데이터)",
        "description": "이것은 API 키가 없을 때 보여지는 예시 레시피입니다. 실제 영상의 내용과는 다를 수 있습니다.",
        "ingredients": [
            "김치 1/4포기",
            "돼지고기 200g",
            "대파 1대",
            "청양고추 1개",
            "두부 1/2모",
            "물 500ml",
            "다진마늘 1큰술",
            "고춧가루 2큰술",
            "국간장 1큰술",
            "새우젓 1작은술"
        ],
        "steps": [
            "돼지고기를 냄비에 넣고 볶아주세요.",
            "고기가 익으면 김치를 넣고 함께 볶습니다.",
            "물을 붓고 끓어오르면 다진마늘, 고춧가루를 넣습니다.",
            "두부와 대파, 청양고추를 넣고 한소끔 더 끓여내면 완성입니다."
        ],
        "tips": [
            "김치는 묵은지를 사용하면 더 맛있습니다.",
            "쌀뜨물을 사용하면 국물 맛이 더 깊어집니다."
        ]
    }

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/bookmarks")
async def get_bookmarks():
    return load_bookmarks()

@app.post("/api/bookmarks")
async def add_bookmark(recipe: Recipe):
    bookmarks = load_bookmarks()
    # Check if already exists (by video_id)
    for b in bookmarks:
        if b.get("video_id") == recipe.video_id:
            return JSONResponse(status_code=400, content={"message": "이미 저장된 레시피입니다."})
    
    new_bookmark = recipe.dict()
    new_bookmark["id"] = str(uuid.uuid4())
    bookmarks.append(new_bookmark)
    save_bookmarks(bookmarks)
    return {"message": "북마크 저장 완료!", "id": new_bookmark["id"]}

@app.delete("/api/bookmarks/{bookmark_id}")
async def delete_bookmark(bookmark_id: str):
    bookmarks = load_bookmarks()
    new_bookmarks = [b for b in bookmarks if b["id"] != bookmark_id]
    if len(bookmarks) == len(new_bookmarks):
        raise HTTPException(status_code=404, message="북마크를 찾을 수 없습니다.")
    
    save_bookmarks(new_bookmarks)
    return {"message": "북마크 삭제 완료!"}

@app.post("/extract")
def extract(url: str = Form(...)):
    print(f"DEBUG: Extract request received for URL: {url}")
    video_id = get_video_id(url)
    if not video_id:
        return JSONResponse(content={"error": "유효하지 않은 YouTube URL입니다."}, status_code=400)

    # 1. Try to get transcript
    transcript = get_transcript(video_id)
    real_title = get_video_title(video_id)
    
    transcript_error = None
    if transcript.startswith("ERROR:"):
        transcript_error = transcript
        transcript = ""

    # 2. Process with Gemini
    if GEMINI_API_KEY:
        if not transcript:
             return JSONResponse(content={"error": f"이 영상에서 자막을 추출할 수 없습니다. (원인: {transcript_error or '알 수 없음'})"}, status_code=500)

        try:
            model = genai.GenerativeModel('gemini-1.5-flash-latest')
            prompt = f"""
            You are a professional chef assistant. Analyze the following cooking video transcript and convert it into a structured recipe.
            
            IMPORTANT RULES:
            1. All output MUST be in Korean (한국어).
            2. Extract ingredients with precise quantities if mentioned.
            3. Break down the cooking process into clear, numbered steps.
            4. Include useful tips mentioned by the chef.
            5. The title MUST be exactly: "{real_title}"
            
            Transcript:
            {transcript[:20000]} 

            Return ONLY a raw JSON object (no markdown formatting, no `json` code blocks) with this schema:
            {{
                "title": "{real_title}",
                "description": "One sentence summary of the dish",
                "ingredients": ["ingredient 1", "ingredient 2"],
                "steps": ["step 1", "step 2"],
                "tips": ["tip 1", "tip 2"]
            }}
            """
            
            print(f"DEBUG: Sending prompt to Gemini (Length: {len(prompt)})")
            response = model.generate_content(prompt)
            text = response.text
            print(f"DEBUG: Raw Gemini Response:\n{text}\n-------------------")

            # Clean up response to ensure it's valid JSON
            # Remove markdown code blocks if present
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            # Strip whitespace
            text = text.strip()
            
            try:
                recipe_data = json.loads(text)
            except json.JSONDecodeError as e:
                print(f"DEBUG: JSON Parse Error: {e}")
                # Try to find JSON object with regex if simple split failed
                match = re.search(r'\{.*\}', text, re.DOTALL)
                if match:
                    print("DEBUG: Attempting regex JSON extraction...")
                    text = match.group(0)
                    recipe_data = json.loads(text)
                else:
                    raise e

            recipe_data["title"] = real_title # Ensure title matches
            recipe_data["video_id"] = video_id
            recipe_data["thumbnail"] = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
            
            # Handle empty fields gracefully
            if not recipe_data.get("ingredients"):
                recipe_data["ingredients"] = ["재료 정보를 찾을 수 없습니다."]
            if not recipe_data.get("steps"):
                recipe_data["steps"] = ["조리 과정을 찾을 수 없습니다."]

            return recipe_data
            
        except Exception as e:
            print(f"DEBUG: Gemini API Error: {e}")
            return JSONResponse(content={"error": f"AI 분석 중 오류가 발생했습니다: {str(e)}"}, status_code=500)
    else:
        # No API Key
        # If running locally without key, user might want to see mock data, 
        # but requested "real" extraction. Return error to prompt key setup.
        return JSONResponse(content={"error": "Gemini API 키가 설정되지 않았습니다. .env 파일을 확인해주세요."}, status_code=500)
