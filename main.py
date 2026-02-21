from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from youtube_transcript_api import YouTubeTranscriptApi
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

# 환경 변수 로드
load_dotenv()

app = FastAPI()

# 정적 파일 및 템플릿 설정
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- [추가] API 키 순환 설정 ---
GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY_1"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3")
]
# 설정된 키만 필터링
GEMINI_KEYS = [k.strip() for k in GEMINI_KEYS if k]
current_key_index = 0


def get_next_gemini_model():
    global current_key_index
    if not GEMINI_KEYS:
        return None

    key = GEMINI_KEYS[current_key_index]
    genai.configure(api_key=key)
    print(f"DEBUG: Using API Key Index {current_key_index}")

    # 다음 호출을 위해 인덱스 변경
    current_key_index = (current_key_index + 1) % len(GEMINI_KEYS)
    return genai.GenerativeModel('gemini-1.5-flash')


# --- [추가] 영상 길이 체크 함수 ---
def check_video_duration(video_id: str) -> int:
    """영상의 길이를 초 단위로 반환합니다."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {'quiet': True, 'no_warnings': True}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get('duration', 0)


# 데이터 모델
class Recipe(BaseModel):
    title: str
    description: Optional[str] = ""
    ingredients: List[str]
    steps: List[str]
    tips: Optional[List[str]] = []
    video_id: str
    thumbnail: Optional[str] = ""


# 유튜브 ID 추출 유틸리티
def get_video_id(url: str) -> Optional[str]:
    pattern = r"(?:v=|\/shorts\/|\/embed\/|\.be\/|\/v\/|\/e\/|watch\?v=|&v=)([^#&?\/]{11})"
    match = re.search(pattern, url)
    return match.group(1) if match else None


def get_video_title(video_id: str) -> str:
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        match = re.search(r'<title>(.*?)</title>', response.text)
        return match.group(1).replace(" - YouTube", "") if match else "YouTube Video"
    except:
        return "YouTube Video"


def get_transcript(video_id: str) -> str:
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
        return " ".join([entry['text'] for entry in transcript_list])
    except Exception as e:
        print(f"DEBUG: Transcript error: {e}")
        return ""


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/extract")
async def extract(url: str = Form(...)):
    video_id = get_video_id(url)
    if not video_id:
        return JSONResponse(content={"error": "유효하지 않은 YouTube URL입니다."}, status_code=400)

    # 1. 영상 길이 제한 (쇼츠/짧은 영상 필터링)
    try:
        duration = check_video_duration(video_id)
        if duration > 120:  # 2분(120초) 이상은 거절
            return JSONResponse(content={"error": f"현재는 2분 이내의 짧은 영상만 분석 가능합니다. (현재 영상: {duration}초)"}, status_code=400)
    except Exception as e:
        print(f"Duration check failed: {e}")

    # 2. 자막 추출
    transcript = get_transcript(video_id)
    if not transcript:
        return JSONResponse(content={"error": "자막을 추출할 수 없는 영상입니다. 자막이 활성화된 영상을 사용해 주세요."}, status_code=500)

    real_title = get_video_title(video_id)

    # 3. API 키 순환하며 분석 시도
    last_error = ""
    for _ in range(len(GEMINI_KEYS)):
        model = get_next_gemini_model()
        if not model: break

        try:
            prompt = f"""
            You are a professional chef. Analyze this cooking video transcript and return a recipe in JSON.
            Output Language: Korean (한국어)
            Title: {real_title}
            Transcript: {transcript[:5000]}

            Return ONLY raw JSON with this schema:
            {{
                "title": "{real_title}",
                "description": "summary",
                "ingredients": ["item 1", "item 2"],
                "steps": ["step 1", "step 2"],
                "tips": ["tip 1"]
            }}
            """

            response = model.generate_content(prompt)
            text = response.text

            # JSON 파싱 (마크다운 제거 로직 포함)
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            recipe_data = json.loads(text.strip())
            recipe_data["video_id"] = video_id
            recipe_data["thumbnail"] = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

            return recipe_data

        except Exception as e:
            last_error = str(e)
            if "429" in last_error:
                print(f"WARN: API Key {current_key_index} exhausted. Trying next...")
                continue
            else:
                break  # 429 외의 오류는 즉시 중단

    return JSONResponse(content={"error": f"AI 분석 실패: {last_error}"}, status_code=500)