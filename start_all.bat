@echo off
chcp 936 >nul
setlocal EnableDelayedExpansion

REM =============================================
REM  LycheeAI LangChain - 一键启动脚本
REM  启动流程：
REM    1. 检查 Docker 服务
REM    2. 启动后端服务
REM    3. 等待后端就绪
REM    4. 打开浏览器
REM =============================================

title LycheeAI LangChain - 启动中...

echo.
echo ============================================
echo   LycheeAI LangChain 版本 - 一键启动
echo ============================================
echo.

REM ---- 配置路径 ----
set "PROJECT=F:\Desktop\面试\智慧果园项目wb\lycheeai_langchain"
set "PYTHON_EXE=F:\miniconda3\envs\lycheeai\python.exe"

REM ---- 检查项目目录 ----
if not exist "%PROJECT%" (
    echo [错误] 项目目录不存在: %PROJECT%
    pause
    exit /b 1
)

REM ---- 检查 Python ----
if not exist "%PYTHON_EXE%" (
    echo [错误] 环境 Python 不存在: %PYTHON_EXE%
    pause
    exit /b 1
)

cd /d "%PROJECT%"
echo [OK] 项目目录: %CD%
echo [OK] Python: %PYTHON_EXE%
echo.

REM ============================================
REM  步骤1：检查 Docker 服务
REM ============================================
echo [1/3] 检查 Docker 服务...
echo --------------------------------------------
docker ps >nul 2>&1
if errorlevel 1 (
    echo [警告] Docker 未运行！请先启动 Docker Desktop。
    echo        Milvus + MySQL + etcd + MinIO 需要 Docker。
    echo.
    choice /c YN /m "是否仍要继续启动？(部分功能可能不可用)"
    if errorlevel 2 exit /b 1
) else (
    echo [OK] Docker 已运行
    REM 检查关键容器
    docker ps --format "{{.Names}}" 2>nul | find "lycheeai-mysql" >nul
    if errorlevel 1 (
        echo [提示] MySQL 容器未运行，正在启动...
        docker-compose up -d
        timeout /t 5 /nobreak >nul
    )
    docker ps --format "{{.Names}}" 2>nul | find "lycheeai-milvus" >nul
    if errorlevel 1 (
        echo [提示] Milvus 容器未运行，正在启动...
        docker-compose up -d
        timeout /t 5 /nobreak >nul
    )
    echo [OK] Docker 服务就绪
)
echo.

REM ============================================
REM  步骤2：清理残留进程
REM ============================================
echo [2/3] 清理残留进程...
echo --------------------------------------------
taskkill /f /fi "WINDOWTITLE eq LycheeAI LangChain*" 2>nul
timeout /t 2 /nobreak >nul
echo [OK] 清理完成
echo.

REM ============================================
REM  步骤3：启动后端服务
REM ============================================
echo [3/3] 启动后端服务（端口18889）...
echo --------------------------------------------

start "LycheeAI LangChain - 后端服务" "%PYTHON_EXE%" main.py

REM 等待后端就绪
set "API_URL=http://localhost:18889/api/health"
set /a wait=0
:wait_api
timeout /t 3 /nobreak >nul
set /a wait+=3

"%PYTHON_EXE%" -c "import httpx; r=httpx.get('%API_URL%',timeout=5); exit(0 if r.status_code==200 else 1)" 2>nul
if not errorlevel 1 (
    echo [OK] 后端服务已就绪（耗时 %wait% 秒）
    goto api_ready
)

if %wait% GEQ 120 (
    echo [错误] 后端服务启动超时（120秒）
    echo        请检查是否有端口冲突或 Docker 服务未启动。
    pause
    exit /b 1
)
echo   等待中... (%wait%s)
goto wait_api
:api_ready

echo.
echo ============================================
echo   所有服务已启动完成！
echo ============================================
echo.
echo   后端地址:     http://localhost:18889
echo   API文档:      http://localhost:18889/docs
echo   前端地址:     http://localhost:18889
echo.
echo   提示：一个黑色命令行窗口已打开，请勿关闭！
echo   停止服务：双击 stop_all.bat
echo.
echo   正在打开浏览器...

timeout /t 2 /nobreak >nul
start "" "http://localhost:18889"

echo.
echo 按任意键退出此窗口（服务窗口请保留）...
pause > nul
endlocal