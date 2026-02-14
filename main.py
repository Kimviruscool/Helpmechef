from fastapi import FastAPI, Request, Form, HTTPException, Body
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
from dotenv import load_dotenv
from pydantic import BaseModel
import uuid
import requests

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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

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
    """Fetches transcript from YouTube."""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
        transcript_text = " ".join([t['text'] for t in transcript_list])
        return transcript_text
    except Exception as e:
        print(f"Error fetching transcript: {e}")
        return ""

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
async def extract(url: str = Form(...)):
    video_id = get_video_id(url)
    if not video_id:
        return JSONResponse(content={"error": "유효하지 않은 YouTube URL입니다."}, status_code=400)

    # 1. Try to get transcript
    transcript = get_transcript(video_id)
    real_title = get_video_title(video_id)
    
    # 2. Process with Gemini
    if GEMINI_API_KEY and transcript:
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = f"""
            You are a professional chef. Analyze the following cooking video transcript and extract the recipe structure.
            The title of the recipe MUST be exactly: "{real_title}"
            
            Return ONLY a JSON object with the following schema:
            {{
                "title": "{real_title}",
                "description": "Short description based on the transcript",
                "ingredients": ["ingredient 1", "ingredient 2", ...],
                "steps": ["step 1", "step 2", ...],
                "tips": ["tip 1", "tip 2", ...]
            }}
            
            Transcript:
            {transcript[:15000]} 
            """
            
            response = model.generate_content(prompt)
            # Clean up response to ensure it's valid JSON
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            recipe_data = json.loads(text)
            recipe_data["title"] = real_title # Encforce real title
            recipe_data["video_id"] = video_id
            recipe_data["thumbnail"] = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
            return recipe_data
            
        except Exception as e:
            # Fallback to mock if API fails
            mock = mock_recipe(video_id)
            mock["title"] = real_title + " (API 오류로 인한 예시)"
            mock["video_id"] = video_id
            mock["thumbnail"] = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
            return mock
    else:
        # No API Key or No Transcript -> Return Mock with a note
        result = mock_recipe(video_id)
        result["title"] = real_title if real_title != "YouTube Video" else result["title"]
        result["video_id"] = video_id
        result["thumbnail"] = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        if not GEMINI_API_KEY:
            result['description'] = "[데모 모드] Gemini API 키가 올바르지 않거나 설정되지 않았습니다."
        elif not transcript:
             result['description'] = "[오류] 자막이 없는 영상이거나 Shorts 자막을 가져올 수 없습니다."
        return result
