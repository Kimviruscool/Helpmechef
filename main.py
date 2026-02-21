from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from youtube_transcript_api import YouTubeTranscriptApi
from google import genai
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

# API 키 리스트 및 로테이션 설정
GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY_1"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3")
]
GEMINI_KEYS = [k.strip() for k in GEMINI_KEYS if k]
current_key_index = 0


class Recipe(BaseModel):
    title: str
    description: Optional[str] = ""
    ingredients: List[str]
    steps: List[str]
    tips: Optional[List[str]] = []
    video_id: str
    thumbnail: Optional[str] = ""


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


if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def get_next_client():
    global current_key_index
    if not GEMINI_KEYS: return None
    api_key = GEMINI_KEYS[current_key_index]
    client = genai.Client(api_key=api_key)
    print(f"🔄 [키 로테이션] {current_key_index + 1}번 키 사용")
    current_key_index = (current_key_index + 1) % len(GEMINI_KEYS)
    return client


# ✅ 영상 정보(제목, 설명, 길이)를 한 번에 가져오는 함수
def get_video_info(video_id: str) -> dict:
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {'quiet': True, 'no_warnings': True}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return {
            "title": info.get('title', '유튜브 요리 영상'),
            "description": info.get('description', ''),
            "duration": info.get('duration', 0)
        }


def get_video_id(url: str) -> Optional[str]:
    pattern = r"(?:v=|\/shorts\/|\/embed\/|\.be\/|\/v\/|\/e\/|watch\?v=|&v=)([^#&?\/]{11})"
    match = re.search(pattern, url)
    return match.group(1) if match else None


def get_transcript(video_id: str) -> str:
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
    video_id = get_video_id(url)
    if not video_id:
        return JSONResponse(status_code=400, content={"error": "유효한 주소가 아닙니다."})

    # 1. 영상 정보 가져오기
    try:
        video_info = get_video_info(video_id)
        if video_info['duration'] > 180:  # 3분 제한
            return JSONResponse(status_code=400, content={"error": "현재는 3분 이내의 짧은 영상만 분석 가능합니다."})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"영상 정보를 불러올 수 없습니다: {str(e)}"})

    # 2. 자막 추출 시도
    transcript = get_transcript(video_id)

    # 3. 데이터 소스 결정 (자막 우선, 없으면 설명란)
    is_transcript_available = bool(transcript)
    source_text = transcript if is_transcript_available else video_info['description']
    data_source_name = "자막" if is_transcript_available else "영상 설명란"

    if not source_text or len(source_text.strip()) < 10:
        return JSONResponse(status_code=400, content={"error": "자막이나 설명란에 분석할 내용이 없습니다."})

    print(f"📊 [데이터 소스] {data_source_name}을 기반으로 분석을 시작합니다.")

    # 4. API 키 순환하며 분석
    last_error = ""
    for _ in range(len(GEMINI_KEYS)):
        client = get_next_client()
        if not client: break

        try:
            target_model = 'gemini-1.5-flash'
            # 자막 유무에 따른 맞춤형 가이드 제공
            analysis_guide = (
                "제공된 자막을 분석하여 레시피를 추출해줘." if is_transcript_available
                else "자막이 없으니, 영상 제목과 설명란에 적힌 텍스트를 바탕으로 레시피를 정리해줘."
            )

            prompt = f"""
            {analysis_guide}
            영상 제목: {video_info['title']}
            내용: {source_text[:6000]}

            반드시 한국어(Korean)로 작성하고, 아래 JSON 형식으로만 응답해:
            {{
                "title": "{video_info['title']}",
                "description": "요리 요약 한문장",
                "ingredients": ["재료명(분량)"],
                "steps": ["1. 조리법", "2. 조리법"],
                "tips": ["맛있게 만드는 팁"]
            }}
            """

            response = client.models.generate_content(model=target_model, contents=prompt)
            res_text = response.text

            if "```" in res_text:
                res_text = re.search(r'\{.*\}', res_text, re.DOTALL).group(0)

            recipe_data = json.loads(res_text)
            recipe_data.update({
                "video_id": video_id,
                "thumbnail": f"[https://img.youtube.com/vi/](https://img.youtube.com/vi/){video_id}/maxresdefault.jpg"
            })

            return recipe_data

        except Exception as e:
            last_error = str(e)
            if "429" in last_error:
                continue
            else:
                break

    return JSONResponse(status_code=500, content={"error": f"AI 분석 실패: {last_error}"})


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