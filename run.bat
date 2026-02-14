@echo off
echo Starting HelpMeChef...
echo.
echo If this is the first time running, make sure you have installed the requirements:
echo pip install -r requirements.txt
echo.
echo Opening browser...
start http://127.0.0.1:8003
echo.
echo Starting server on port 8003...
python -m uvicorn main:app --reload --port 8003
pause
