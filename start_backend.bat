@echo off
setlocal EnableDelayedExpansion

REM PowerShell 检测（% 在 PS 中被当作 foreach 别名）
echo %PSModulePath% | findstr /i "PowerShell" >nul 2>&1
if not errorlevel 1 (
    echo [INFO] 检测到 PowerShell 环境，正在调用 start_backend.ps1...
    powershell -ExecutionPolicy Bypass -File "%~dp0start_backend.ps1"
    exit /b %errorlevel%
)

title LycheeAI RAG - Backend

set "PROJECT=E:\github_project\lycheeai_rag"
set "PYTHON_EXE=E:\miniconda3\envs\lycheeai\python.exe"
set "API_PORT=18888"

cd /d "%PROJECT%"

echo.
echo ============================================
echo   LycheeAI RAG - Backend Server
echo ============================================
echo.
echo   Port: %API_PORT%
echo   URL:  http://localhost:%API_PORT%
echo   API:  http://localhost:%API_PORT%/docs
echo.

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python not found: %PYTHON_EXE%
    pause
    exit /b 1
)

echo Starting backend...
"%PYTHON_EXE%" main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Backend exited with code: !ERRORLEVEL!
)
pause