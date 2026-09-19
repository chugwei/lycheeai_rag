@echo off
title LycheeAI RAG - Stop Services

REM PowerShell 检测
echo %PSModulePath% | findstr /i "PowerShell" >nul 2>&1
if not errorlevel 1 (
    echo [INFO] 检测到 PowerShell 环境，正在调用 stop_all.ps1...
    powershell -ExecutionPolicy Bypass -File "%~dp0stop_all.ps1"
    exit /b %errorlevel%
)

echo ========================================
echo   LycheeAI RAG - Stop All Services
echo ========================================
echo.

echo [1/2] Stopping backend (LycheeAI RAG)...
taskkill /f /fi "WINDOWTITLE eq LycheeAI RAG*" 2>nul
echo   - Done

echo [2/2] Stopping main.py processes...
taskkill /f /fi "IMAGENAME eq python.exe" /fi "CMD eq *main*" 2>nul
echo   - Done

echo.
echo Waiting for processes to exit...
timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo   All services stopped
echo   Port 18888 released
echo ========================================
echo.
pause