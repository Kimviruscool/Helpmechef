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

# ✅ [1단계] Gemini API 연결 확인 및 클라이언트 초기화 # 수정
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = None

if GEMINI_API_KEY:
    try:
        GEMINI_API_KEY = GEMINI_API_KEY.strip()
        # google-genai 최신 방식 클라이언트 생성 # 수정
        client = genai.Client(api_key=GEMINI_API_KEY)
        print(f"\n✅ [1단계: 연결 확인] Gemini API 클라이언트 로드 성공!")
        print(f"   - API Key: {GEMINI_API_KEY[:10]}**********")

        # 사용 가능한 모델 목록을 콘솔에 출력하여 404 에러 방지용 확인 # 수정
        print("🔎 [참고] 사용 가능한 모델 리스트를 확인합니다...")
        for m in client.models.list():
            if 'generateContent' in m.supported_methods:
                print(f"   - 사용 가능 모델: {m.name}")
    except Exception as e:
        print(f"❌ [1단계: 에러] API 연결 설정 중 오류: {e}")
else:
    print("❌ [1단계: 에러] .env 파일에서 GEMINI_API_KEY를 찾을 수 없습니다.")


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
        return "자막을 직접 추출할 수 없어 제목 기반으로 분석합니다."


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/extract")
async def extract_recipe(url: str = Form(...)):
    # ✅ [2단계] 콘솔로 주소를 받는다 # 수정
    print(f"\n" + "=" * 60)
    print(f"🔗 [2단계: 주소 수신] 웹 화면으로부터 URL을 받았습니다: {url}")

    video_id = get_video_id(url)
    if not video_id:
        print("❌ [오류] 잘못된 유튜브 URL 형식입니다.")
        return JSONResponse(status_code=400, content={"error": "유효한 주소가 아닙니다."})

    transcript = get_transcript(video_id)
    title = get_video_title(video_id)

    # ✅ [3단계] 받은 주소/자막 데이터가 API에 보내지는지 확인 # 수정
    # 404 에러 해결을 위해 모델명을 'gemini-2.0-flash'로 변경 # 수정
    target_model = 'gemini-2.0-flash'
    print(f"📨 [3단계: API 전송] Gemini API({target_model})로 분석 요청을 보냅니다...")
    print(f"   - 분석 대상 제목: {title}")

    try:
        prompt = f"""
        영상 제목: {title}
        자막 내용: {transcript[:8000]}

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

        # 최신 SDK 호출 방식 적용 # 수정
        response = client.models.generate_content(
            model=target_model,
            contents=prompt
        )

        # ✅ [4단계] 제미나이가 레시피를 가져오는지 확인 # 수정
        print(f"📥 [4단계: 데이터 수신] Gemini로부터 응답 데이터를 성공적으로 받았습니다.")

        res_text = response.text
        # JSON 포맷팅 제거 (마크다운 대응) # 수정
        if "```" in res_text:
            res_text = re.search(r'\{.*\}', res_text, re.DOTALL).group(0)

        recipe_data = json.loads(res_text)
        print(f"   - 레시피 이름: {recipe_data.get('title')}")
        print(f"   - 재료 리스트: {', '.join(recipe_data.get('ingredients', [])[:3])}...")

        # 메타데이터 추가
        recipe_data.update({
            "video_id": video_id,
            "thumbnail": f"[https://img.youtube.com/vi/](https://img.youtube.com/vi/){video_id}/maxresdefault.jpg"
        })

        # ✅ [5단계] 가져온 레시피를 웹으로 보내는지 확인 # 수정
        print(f"📤 [5단계: 웹 전송] 분석된 데이터를 웹 브라우저로 최종 전송합니다.")
        print("=" * 60 + "\n")

        return recipe_data

    except Exception as e:
        print(f"❌ [에러] 4단계 혹은 5단계 진행 중 오류 발생: {e}")
        # 상세 에러 로그 출력 # 수정
        if "404" in str(e):
            print("   💡 해결 팁: 모델명이 현재 사용 불가능할 수 있습니다. 위 로그의 '사용 가능 모델 리스트'를 확인하세요.")
        return JSONResponse(status_code=500, content={"error": f"AI 분석 중 오류: {str(e)}"})


# 북마크 관련 엔드포인트
@app.get("/api/bookmarks")
async def get_bookmarks():
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
    print(f"⭐ [북마크] {recipe.title} 저장 완료")
    return {"message": "저장 완료"}


# 서버 실행 코드 추가 # 수정
if __name__ == "__main__":
    print("\n🚀 [서버 시작] [http://127.0.0.1:8000](http://127.0.0.1:8000) 에서 실행 중...")
    uvicorn.run(app, host="127.0.0.1", port=8000)