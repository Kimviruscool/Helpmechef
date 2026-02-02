from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles # 정적 파일이 필요한 경우

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def home(request: Request):
    # templates/index.html 파일을 화면에 띄웁니다.
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/extract")
async def extract(url: str = Form(...)):
    # 여기에 나중에 크롤링 + Gemini + Notion 로직을 넣을 겁니다.
    # 지금은 잘 작동하는지 테스트용 응답만 보냅니다.
    return {"message": "노션으로 레시피 전송 완료! 노션 페이지를 확인하세요."}