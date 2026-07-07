@echo off
chcp 936 >nul
setlocal EnableDelayedExpansion

title LycheeAI LangChain - Vue3 前端

set "PROJECT=F:\Desktop\面试\智慧果园项目wb\lycheeai_langchain"
set "PYTHON_EXE=F:\miniconda3\envs\lycheeai\python.exe"

cd /d "%PROJECT%"

echo.
echo ============================================
echo   LycheeAI LangChain 版本 - Vue3 前端启动
echo ============================================
echo.
echo   Vue3 前端由后端 (18889端口) 直接提供
echo   访问地址: http://localhost:18889
echo   API文档:  http://localhost:18889/docs
echo.

REM ---- 检查后端是否在运行 ----
echo 正在检查后端服务...
"%PYTHON_EXE%" -c "import httpx; r=httpx.get('http://localhost:18889/api/health',timeout=5); exit(0)" 2>nul
if errorlevel 1 (
    echo [提示] 后端未运行，正在启动...
    start "LycheeAI LangChain - 后端服务" "%PYTHON_EXE%" main.py
    echo 等待后端就绪...
    choice /t 8 /d y /n >nul
) else (
    echo [OK] 后端服务已就绪
)

echo.
echo ============================================
echo   [OK] 正在打开前端...
echo   地址: http://localhost:18889
echo ============================================
echo.
start http://localhost:18889
echo 如果浏览器未自动打开，请手动访问:
echo   http://localhost:18889
echo.
pause