@echo off
setlocal EnableDelayedExpansion

REM =============================================
REM  LycheeAI RAG - One-click startup
REM =============================================

REM 检测是否在 PowerShell 中运行（% 在 PS 中被当作 foreach 别名）
REM 如果是，自动调用 start_all.ps1
echo %PSModulePath% | findstr /i "PowerShell" >nul 2>&1
if not errorlevel 1 (
    echo [INFO] 检测到 PowerShell 环境，正在调用 start_all.ps1...
    powershell -ExecutionPolicy Bypass -File "%~dp0start_all.ps1"
    exit /b %errorlevel%
)

title LycheeAI RAG - Starting...

echo.
echo ============================================
echo   LycheeAI RAG System
echo ============================================
echo.

set "PROJECT=E:\github_project\lycheeai_rag"
set "PYTHON_EXE=E:\miniconda3\envs\lycheeai\python.exe"
set "API_PORT=18888"

if not exist "%PROJECT%" (
    echo [ERROR] Project directory not found: %PROJECT%
    pause
    exit /b 1
)

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python interpreter not found: %PYTHON_EXE%
    pause
    exit /b 1
)

cd /d "%PROJECT%"

REM ---- Menu ----
echo Choose an option:
echo.
echo   1. Start all services
echo   2. Rebuild indexes (BM25 + vector)
echo   3. Cancel
echo.
choice /c 123 /n /m "Enter [1/2/3]: "
if errorlevel 3 exit /b 0
if errorlevel 2 goto rebuild
if errorlevel 1 goto start_services

REM =============================================
REM  Option 2: Rebuild indexes
REM =============================================
:rebuild
echo.
echo ============================================
echo   Rebuilding indexes...
echo ============================================
echo.
"%PYTHON_EXE%" scripts\build_index.py
if errorlevel 1 (
    echo [ERROR] Index rebuild failed
    pause
    exit /b 1
)
echo.
echo [OK] Index rebuilt successfully
pause
exit /b 0

REM =============================================
REM  Option 1: Start all services
REM =============================================
:start_services
echo.
echo [1/3] Docker containers...
echo --------------------------------------------

REM 读取 VECTOR_DB_TYPE，若为 chroma 则跳过 Docker
set "VECTOR_DB_TYPE=chroma"
if exist "%PROJECT%\.env" (
    for /f "tokens=2 delims==" %%a in ('findstr /b "VECTOR_DB_TYPE" "%PROJECT%\.env" 2^>nul') do set "VECTOR_DB_TYPE=%%a"
)

if /i "%VECTOR_DB_TYPE%"=="chroma" (
    echo [INFO] ChromaDB 模式 - 无需 Docker 容器
) else (
    docker ps >nul 2>&1
    if errorlevel 1 (
        echo [INFO] Docker not available - using local ChromaDB
    ) else (
        echo [OK] Docker running, checking containers...
        docker ps --format "{{.Names}}" 2>nul | find "lycheeai-mysql" >nul
        if errorlevel 1 (
            echo [INFO] Starting MySQL...
            docker-compose up -d mysql
            timeout /t 5 /nobreak >nul
        )
        docker ps --format "{{.Names}}" 2>nul | find "lycheeai-milvus" >nul
        if errorlevel 1 (
            echo [INFO] Starting Milvus...
            docker-compose up -d milvus etcd minio
            timeout /t 5 /nobreak >nul
        )
        echo [OK] Docker containers ready
    )
)
echo.

echo [2/3] Cleaning old processes...
echo --------------------------------------------
taskkill /f /fi "WINDOWTITLE eq LycheeAI RAG - Backend" 2>nul
timeout /t 2 /nobreak >nul
echo [OK] Cleanup done
echo.

echo [3/3] Starting backend (port %API_PORT%)...
echo --------------------------------------------

start /min "LycheeAI RAG - Backend" "%PYTHON_EXE%" main.py

set "API_URL=http://localhost:%API_PORT%/api/health"
set /a wait=0
:wait_api
timeout /t 3 /nobreak >nul
set /a wait+=3

"%PYTHON_EXE%" -c "import httpx; r=httpx.get('%API_URL%',timeout=5); exit(0 if r.status_code==200 else 1)" 2>nul
if not errorlevel 1 (
    echo [OK] Backend ready (%wait%s)
    goto api_ready
)

if %wait% GEQ 180 (
    echo [ERROR] Backend startup timeout (180s)
    echo         The first startup may take longer due to model downloads.
    pause
    exit /b 1
)
echo   Waiting... (%wait%s)
goto wait_api
:api_ready

echo.
echo ============================================
echo   All services started!
echo ============================================
echo.
echo   Backend:  http://localhost:%API_PORT%
echo   API docs: http://localhost:%API_PORT%/docs
echo.
echo   Stop:  double-click stop_all.bat
echo.

timeout /t 2 /nobreak >nul
start "" "http://localhost:%API_PORT%"

echo Press any key to close this window (backend stays open)...
pause > nul
endlocal