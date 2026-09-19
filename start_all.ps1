<#
.SYNOPSIS
  LycheeAI RAG 一键启动脚本 (PowerShell 7 兼容)
.DESCRIPTION
  启动后端服务，可选重建索引。
  在 PowerShell 中直接运行：.\start_all.ps1
#>

$PROJECT = "E:\github_project\lycheeai_rag"
$PYTHON_EXE = "E:\miniconda3\envs\lycheeai\python.exe"
$API_PORT = 18888

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "  LycheeAI RAG System" -ForegroundColor Cyan
Write-Host "============================================`n" -ForegroundColor Cyan

if (-not (Test-Path $PROJECT)) {
    Write-Host "[ERROR] Project directory not found: $PROJECT" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

if (-not (Test-Path $PYTHON_EXE)) {
    Write-Host "[ERROR] Python interpreter not found: $PYTHON_EXE" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Set-Location $PROJECT

# ─── 菜单 ───
Write-Host "Choose an option:" -ForegroundColor Yellow
Write-Host "`n  1. Start all services"
Write-Host "  2. Rebuild indexes (BM25 + vector)"
Write-Host "  3. Cancel`n"

$choice = Read-Host "Enter [1/2/3]"
switch ($choice) {
    "2" { & $PSScriptRoot\start_all.ps1 -Rebuild; return }
    "3" { exit 0 }
    default { }
}

# ─── 启动服务 ───
Write-Host "`n[1/3] Docker containers..." -ForegroundColor Yellow
Write-Host "--------------------------------------------"

# 读取 VECTOR_DB_TYPE
$envFile = "$PROJECT\.env"
$vectorDbType = "chroma"
if (Test-Path $envFile) {
    $match = Select-String -Path $envFile -Pattern "^VECTOR_DB_TYPE=(.+)" -SimpleMatch
    if ($match) {
        $vectorDbType = $match.Matches.Groups[1].Value.Trim()
    }
}

if ($vectorDbType -eq "chroma") {
    Write-Host "[INFO] ChromaDB 模式 - 无需 Docker 容器" -ForegroundColor Green
} else {
    $dockerOk = $true
    try { docker ps *>$null } catch { $dockerOk = $false }
    if (-not $dockerOk) {
        Write-Host "[INFO] Docker not available - using local ChromaDB" -ForegroundColor Yellow
    } else {
        Write-Host "[OK] Docker running, checking containers..." -ForegroundColor Green
        $containers = docker ps --format "{{.Names}}" 2>$null
        if ($containers -notcontains "lycheeai-mysql") {
            Write-Host "[INFO] Starting MySQL..." -ForegroundColor Yellow
            docker-compose up -d mysql
            Start-Sleep -Seconds 5
        }
        if ($containers -notcontains "lycheeai-milvus") {
            Write-Host "[INFO] Starting Milvus..." -ForegroundColor Yellow
            docker-compose up -d milvus etcd minio
            Start-Sleep -Seconds 5
        }
        Write-Host "[OK] Docker containers ready" -ForegroundColor Green
    }
}

Write-Host "`n[2/3] Cleaning old processes..." -ForegroundColor Yellow
Write-Host "--------------------------------------------"
# 停止旧的后端进程（通过端口号）
$oldPid = $null
try {
    $netstat = netstat -ano | Select-String ":${API_PORT}.*LISTENING"
    if ($netstat) {
        $oldPid = [int]($netstat.ToString() -split '\s+')[-1]
    }
} catch { }

if ($oldPid) {
    Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Write-Host "[OK] Port $API_PORT released" -ForegroundColor Green
} else {
    # 也通过窗口标题尝试
    $oldProcess = Get-Process | Where-Object { $_.MainWindowTitle -like "*LycheeAI RAG*" -and $_.ProcessName -eq "python" }
    if ($oldProcess) {
        $oldProcess | Stop-Process -Force
        Start-Sleep -Seconds 2
        Write-Host "[OK] Old backend stopped" -ForegroundColor Green
    } else {
        Write-Host "[OK] No old process found" -ForegroundColor Green
    }
}
Start-Sleep -Seconds 2

Write-Host "`n[3/3] Starting backend (port $API_PORT)..." -ForegroundColor Yellow
Write-Host "--------------------------------------------"

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $PYTHON_EXE
$psi.Arguments = "main.py"
$psi.WorkingDirectory = $PROJECT
$psi.UseShellExecute = $true
$psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Minimized
$psi.CreateNoWindow = $false
$process = [System.Diagnostics.Process]::Start($psi)

Write-Host "[INFO] Backend process started, waiting for API..." -ForegroundColor Yellow

# 等待后端就绪（最多 180s）
$apiUrl = "http://localhost:${API_PORT}/api/health"
$wait = 0
while ($wait -lt 180) {
    Start-Sleep -Seconds 3
    $wait += 3
    try {
        $response = Invoke-WebRequest -Uri $apiUrl -TimeoutSec 5 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Write-Host "[OK] Backend ready (${wait}s)" -ForegroundColor Green
            break
        }
    } catch {
        # 还没就绪
    }
    Write-Host "  Waiting... (${wait}s)" -ForegroundColor Gray
}

if ($wait -ge 180) {
    Write-Host "[ERROR] Backend startup timeout (180s)" -ForegroundColor Red
    Write-Host "        The first startup may take longer due to model downloads." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "  All services started!" -ForegroundColor Cyan
Write-Host "============================================`n" -ForegroundColor Cyan
Write-Host "  Backend:  http://localhost:${API_PORT}"
Write-Host "  API docs: http://localhost:${API_PORT}/docs`n"
Write-Host "  Stop:  double-click stop_all.bat`n"

Start-Sleep -Seconds 2
Start-Process "http://localhost:${API_PORT}"

Read-Host "Press Enter to close this window (backend stays open)..."