<#
.SYNOPSIS
  LycheeAI RAG 停止脚本 (PowerShell 7 兼容)
#>

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  LycheeAI RAG - Stop All Services" -ForegroundColor Cyan
Write-Host "========================================`n"

# 通过端口 18888 找到后端进程
Write-Host "[1/2] Stopping backend (port 18888)..." -ForegroundColor Yellow
try {
    $netstat = netstat -ano | Select-String ":18888.*LISTENING"
    if ($netstat) {
        $pid = [int]($netstat.ToString() -split '\s+')[-1]
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Write-Host "  - Stopped PID $pid" -ForegroundColor Green
    } else {
        Write-Host "  - No process found on port 18888" -ForegroundColor Gray
    }
} catch {
    Write-Host "  - Error finding process" -ForegroundColor Red
}

# 也停掉 main.py 进程
Write-Host "[2/2] Stopping main.py processes..." -ForegroundColor Yellow
try {
    Get-Process | Where-Object {
        $_.ProcessName -eq "python" -and $_.CommandLine -like "*main.py*"
    } | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "  - Done" -ForegroundColor Green
} catch {
    Write-Host "  - No additional processes" -ForegroundColor Gray
}

Write-Host "`n[OK] All services stopped" -ForegroundColor Green
Read-Host "Press Enter to exit"