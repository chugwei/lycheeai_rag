@echo off
setlocal EnableDelayedExpansion

title LycheeAI RAG - Frontend

set "PROJECT=E:\github_project\lycheeai_rag"
set "PYTHON_EXE=E:\miniconda3\envs\lycheeai\python.exe"
set "API_PORT=18888"

cd /d "%PROJECT%"

echo.
echo ============================================
echo   LycheeAI RAG - Frontend Launcher
echo ============================================
echo.
echo   Backend: http://localhost:%API_PORT%
echo   API:     http://localhost:%API_PORT%/docs
echo.

REM Check if backend is running
echo Checking backend status...
"%PYTHON_EXE%" -c "import httpx; r=httpx.get('http://localhost:%API_PORT%/api/health',timeout=5); exit(0)" 2>nul
if errorlevel 1 (
    echo [INFO] Backend not running, starting it...
    start "LycheeAI RAG - Backend" "%PYTHON_EXE%" main.py
    echo Waiting for backend...
    choice /t 8 /d y /n >nul
) else (
    echo [OK] Backend is running
)

echo.
echo ============================================
echo   Opening browser...
echo   URL: http://localhost:%API_PORT%
echo ============================================
echo.
start http://localhost:%API_PORT%
echo If browser doesn't open, manually visit:
echo   http://localhost:%API_PORT%
echo.
pause