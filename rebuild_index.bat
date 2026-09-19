@echo off
setlocal EnableDelayedExpansion

title LycheeAI - 索引重建中...

set "PROJECT=E:\github_project\lycheeai_rag"
set "PYTHON_EXE=E:\miniconda3\envs\lycheeai\python.exe"

echo ============================================
echo   LycheeAI - 索引重建工具
echo ============================================
echo.
echo   This will rebuild:
echo     1. BM25 关键词索引
echo     2. ChromaDB 向量索引
echo     3. 分块缓存 (chunks_cache.json)
echo.
echo   Source: %PROJECT%\data\raw\
echo.
echo   Press Ctrl+C to cancel, or any key to continue...
pause > nul
echo.

cd /d "%PROJECT%"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python not found: %PYTHON_EXE%
    pause
    exit /b 1
)

echo [Step 1/1] Building all indexes...
echo   (This may take several minutes for 28+ PDFs)
echo.

"%PYTHON_EXE%" scripts\build_index.py

if errorlevel 1 (
    echo.
    echo [ERROR] Index build failed. Check the error message above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   ✓ 索引重建完成！
echo ============================================
echo.
echo   You can now restart the backend:
echo     start_backend.bat
echo.
pause