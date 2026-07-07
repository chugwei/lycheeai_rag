@echo off
chcp 936 >nul
setlocal EnableDelayedExpansion

title LycheeAI LangChain - 后端服务

set "PROJECT=F:\Desktop\面试\智慧果园项目wb\lycheeai_langchain"
set "PYTHON_EXE=F:\miniconda3\envs\lycheeai\python.exe"

cd /d "%PROJECT%"

echo.
echo ============================================
echo   LycheeAI LangChain 版本 - 后端服务启动
echo ============================================
echo.
echo   端口: 18889
echo   地址: http://localhost:18889
echo   API:  http://localhost:18889/docs
echo.

if not exist "%PYTHON_EXE%" (
    echo [错误] Python 不存在: %PYTHON_EXE%
    pause
    exit /b 1
)

echo 正在启动后端...
"%PYTHON_EXE%" main.py

if errorlevel 1 (
    echo.
    echo [错误] 后端服务异常退出 (错误码: !ERRORLEVEL!)
)
pause