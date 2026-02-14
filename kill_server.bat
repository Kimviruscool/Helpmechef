@echo off
echo Killing all HelpMeChef processes...
taskkill /F /IM python.exe /T
taskkill /F /IM uvicorn.exe /T
echo Server killed.
echo To restart, run run.bat
pause
