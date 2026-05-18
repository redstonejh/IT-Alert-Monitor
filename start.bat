@echo off
cd /d "%~dp0"
echo Starting ESET Alert Monitor...
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
