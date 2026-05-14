@echo off
cd /d "%~dp0"
if not exist .env (
    echo Create .env from .env.example and fill in your data
    pause
    exit /b 1
)

echo Starting bot in background...
start "Bot" /min pythonw main.py 2>nul || start "Bot" /min python main.py

timeout /t 2 /nobreak >nul

echo Starting web panel...
start "Web" /min pythonw web.py 2>nul || start "Web" /min python web.py

echo.
echo Bot and web panel started.
echo Web: http://81.17.154.153:5000 (or this PC IP)
echo Close this window to keep them running. To stop: close "Bot" and "Web" windows.
pause
