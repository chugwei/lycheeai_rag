@echo off
chcp 936 >nul
title LycheeAI LangChain - 停止服务

echo ========================================
echo   LycheeAI LangChain - 停止所有服务
echo ========================================
echo.

echo 正在查找并停止 Python 进程...
echo.

echo [1/2] 停止后端服务 (lycheeai_langchain.main)...
taskkill /f /fi "WINDOWTITLE eq LycheeAI LangChain*" 2>nul
taskkill /f /fi "IMAGENAME eq python.exe" /fi "CMD eq *lycheeai_langchain*" 2>nul
echo   - 已发送停止信号

echo [2/2] 停止其他 Python 进程...
taskkill /f /fi "IMAGENAME eq python.exe" /fi "CMD eq *main*" 2>nul
echo   - 已发送停止信号

echo.
echo 正在等待进程退出...
timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo   所有服务已停止
echo   端口 18889 已释放
echo ========================================
echo.
pause