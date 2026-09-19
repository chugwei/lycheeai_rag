<#
.SYNOPSIS
  LycheeAI RAG 后端启动脚本 (PowerShell 7 兼容)
#>

$PROJECT = "E:\github_project\lycheeai_rag"
$PYTHON_EXE = "E:\miniconda3\envs\lycheeai\python.exe"
$API_PORT = 18888

Set-Location $PROJECT

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "  LycheeAI RAG - Backend Server" -ForegroundColor Cyan
Write-Host "============================================`n" -ForegroundColor Cyan
Write-Host "  Port: $API_PORT"
Write-Host "  URL:  http://localhost:$API_PORT"
Write-Host "  API:  http://localhost:$API_PORT/docs`n"

if (-not (Test-Path $PYTHON_EXE)) {
    Write-Host "[ERROR] Python not found: $PYTHON_EXE" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Starting backend..." -ForegroundColor Yellow

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $PYTHON_EXE
$psi.Arguments = "main.py"
$psi.WorkingDirectory = $PROJECT
$psi.UseShellExecute = $true
$psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Minimized
[System.Diagnostics.Process]::Start($psi)

if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
    Write-Host "`n[ERROR] Backend exited with code: $LASTEXITCODE" -ForegroundColor Red
}

Read-Host "Press Enter to exit"