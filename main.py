from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from youtube_transcript_api import YouTubeTranscriptApi
from google import genai  # 최신 SDK 사용
from dotenv import load_dotenv
from pydantic import BaseModel
from yt_dlp import YoutubeDL
import uvicorn
import uuid
import requests
import os
import json
import re
import html
from typing import List, Dict, Optional

# 환경 변수 로드
load_dotenv()

app = FastAPI(title="Help me Chef's")

# ✅ [수정] API 키 리스트 및 로테이션 설정
GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY_1"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3")
]
GEMINI_KEYS = [k.strip() for k in GEMINI_KEYS if k]  # 비어있지 않은 키만 추출
current_key_index = 0


# 데이터 모델
class Recipe(BaseModel):
    title: str
    description: Optional[str] = ""
    ingredients: List[str]
    steps: List[str]
    tips: Optional[List[str]] = []
    video_id: str
    thumbnail: Optional[str] = ""


# 북마크 관리 함수
BOOKMARKS_FILE = "bookmarks.json"


def load_bookmarks():
    if not os.path.exists(BOOKMARKS_FILE): return []
    try:
        with open(BOOKMARKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_bookmarks(bookmarks):
    with open(BOOKMARKS_FILE, "w", encoding="utf-8") as f:
        json.dump(bookmarks, f, ensure_ascii=False, indent=2)


# 정적 파일 및 템플릿 설정
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ✅ [수정] 다음 클라이언트를 가져오는 함수 (로테이션)
def get_next_client():
    global current_key_index
    if not GEMINI_KEYS:
        return None

    api_key = GEMINI_KEYS[current_key_index]
    client = genai.Client(api_key=api_key)
    print(f"🔄 [키 로테이션] 현재 {current_key_index + 1}번 API 키 사용 중...")

    current_key_index = (current_key_index + 1) % len(GEMINI_KEYS)
    return client


# ✅ [추가] 영상 길이 체크 (쇼츠 판별용)
def check_video_duration(video_id: str) -> int:
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {'quiet': True, 'no_warnings': True}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get('duration', 0)


def get_video_id(url: str) -> Optional[str]:
    pattern = r"(?:v=|\/shorts\/|\/embed\/|\.be\/|\/v\/|\/e\/|watch\?v=|&v=)([^#&?\/]{11})"
    match = re.search(pattern, url)
    return match.group(1) if match else None


def get_video_title(video_id: str) -> str:
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code == 200:
            match = re.search(r'<title>(.*?)</title>', response.text)
            if match:
                return html.unescape(match.group(1).replace(" - YouTube", ""))
    except:
        pass
    return "유튜브 요리 영상"


def get_transcript(video_id: str) -> str:
    print(f"🔍 [진행] 자막 추출을 시도합니다... (ID: {video_id})")
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
        return " ".join([entry['text'] for entry in transcript_list])
    except:
        return ""


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/extract")
async def extract_recipe(url: str = Form(...)):
    print(f"\n" + "=" * 60)
    print(f"🔗 [수신] 웹 화면으로부터 URL을 받았습니다: {url}")

    video_id = get_video_id(url)
    if not video_id:
        return JSONResponse(status_code=400, content={"error": "유효한 주소가 아닙니다."})

    # ✅ [추가] 길이 체크 로직 (2분 이내만 허용)
    try:
        duration = check_video_duration(video_id)
        print(f"⏱️ [길이 확인] 영상 시간: {duration}초")
        if duration > 120:
            return JSONResponse(status_code=400, content={"error": "현재는 2분 이내의 짧은 영상만 분석 가능합니다."})
    except:
        print("⚠️ 영상 길이를 확인할 수 없습니다. 계속 진행합니다.")

    transcript = get_transcript(video_id)
    if not transcript:
        return JSONResponse(status_code=500, content={"error": "자막이 없는 영상은 분석할 수 없습니다."})

    title = get_video_title(video_id)
    target_model = 'gemini-1.5-flash'  # 무료 할당량이 더 여유로운 1.5-flash 권장

    # ✅ [수정] API 키 개수만큼 루프를 돌며 시도 (429 에러 대응)
    last_error = ""
    for _ in range(len(GEMINI_KEYS)):
        client = get_next_client()
        if not client:
            return JSONResponse(status_code=500, content={"error": "API 키가 설정되지 않았습니다."})

        try:
            print(f"📨 [전송] Gemini API({target_model}) 분석 요청 중...")
            prompt = f"""
            영상 제목: {title}
            자막 내용: {transcript[:6000]}

            위 내용을 바탕으로 한국어 요리 레시피를 작성해줘. 
            반드시 JSON 형식으로만 응답하고 다른 말은 하지 마:
            {{
                "title": "{title}",
                "description": "요리 요약",
                "ingredients": ["재료(분량)"],
                "steps": ["조리과정"],
                "tips": ["팁"]
            }}
            """

            response = client.models.generate_content(
                model=target_model,
                contents=prompt
            )

            res_text = response.text
            if "```" in res_text:
                res_text = re.search(r'\{.*\}', res_text, re.DOTALL).group(0)

            recipe_data = json.loads(res_text)
            recipe_data.update({
                "video_id": video_id,
                "thumbnail": f"[https://img.youtube.com/vi/](https://img.youtube.com/vi/){video_id}/maxresdefault.jpg"
            })

            print(f"📤 [완료] 분석된 데이터를 성공적으로 전송합니다.")
            return recipe_data

        except Exception as e:
            last_error = str(e)
            if "429" in last_error:
                print(f"⚠️ 한도 초과(429) 발생! 다음 API 키로 전환합니다...")
                continue
            else:
                print(f"❌ 분석 오류 발생: {last_error}")
                break

    return JSONResponse(status_code=500, content={"error": f"모든 API 한도를 초과했거나 오류가 발생했습니다: {last_error}"})


# 북마크 관련 엔드포인트
@app.get("/api/bookmarks")
async def get_bookmarks_api():
    return load_bookmarks()


@app.post("/api/bookmarks")
async def add_bookmark(recipe: Recipe):
    bookmarks = load_bookmarks()
    if any(b['video_id'] == recipe.video_id for b in bookmarks):
        return JSONResponse(status_code=400, content={"message": "이미 저장된 레시피입니다."})
    new_data = recipe.dict()
    new_data['id'] = str(uuid.uuid4())
    bookmarks.append(new_data)
    save_bookmarks(bookmarks)
    return {"message": "저장 완료"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)