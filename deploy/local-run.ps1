# 无需 Docker 的 Windows 本机生产模式启动脚本（job-ability-graph）
#
# 作用：在宿主机上以“生产形态”运行——
#   1. Neo4j（便携版，scripts/neo4j_local.ps1，未运行则自动启动）
#   2. 后端 FastAPI（uvicorn，127.0.0.1:8002，读取仓库根 .env 配置）
#   3. 前端（先 npm run build 出 frontend/dist，再用 node 静态服务器 +
#      /api 反代托管，访问 http://127.0.0.1:5173）
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File deploy\local-run.ps1
#   powershell -ExecutionPolicy Bypass -File deploy\local-run.ps1 -SkipBuild   # 复用已构建的 dist
#   powershell -ExecutionPolicy Bypass -File deploy\local-run.ps1 -WebPort 3000 -BackendPort 8002
#   按 Enter 退出并自动清理两个子进程。
#
# 前置条件（与 STARTUP.md 一致）：
#   - backend/venv 或系统 Python 已装依赖；仓库根存在 .env（GRAPH_BACKEND=neo4j 等）
#   - Node.js 18+；Ollama 已装并 qwen2.5:7b 已拉取（若用 LLM 功能）

[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [int]$WebPort = 5173,
    [int]$BackendPort = 8002,
    [switch]$SkipBuild,
    [switch]$SkipNeo4jCheck,
    [switch]$NoOllama
)

$ErrorActionPreference = "Stop"
$tmp = Join-Path $env:TEMP "job-ability-deploy"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

function Test-Port([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync("127.0.0.1", $Port)
        return $task.Wait(600)
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

Write-Host "==> repo: $RepoRoot"

# ── 0) Python（优先 backend/venv） ────────────────────────────────────────
$venvPy = Join-Path $RepoRoot "backend\venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $python = $venvPy
    Write-Host "==> python: backend\venv"
} else {
    $python = (Get-Command python -ErrorAction Stop).Source
    Write-Host "==> python: $python  (未找到 backend\venv，使用系统 Python)"
}

# ── 1) Neo4j ───────────────────────────────────────────────────────────────
if (-not $SkipNeo4jCheck) {
    if (Test-Port 7687) {
        Write-Host "==> Neo4j: 已在运行 (bolt 7687)"
    } else {
        Write-Host "==> Neo4j: 未运行，调用 scripts\neo4j_local.ps1 start ..."
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "scripts\neo4j_local.ps1") start
        if (-not (Test-Port 7687)) { Write-Warning "Neo4j 未就绪，图谱检索会失败；请检查 D:\neo4j" }
    }
}

# ── 2) Ollama（可选，供 LLM 画像/报告使用） ───────────────────────────────
if (-not $NoOllama -and -not (Test-Port 11434)) {
    Write-Warning "宿主机 Ollama 未运行 (11434)。画像生成/匹配报告等功能会降级或报错。"
    Write-Host "    如需完整功能：先启动 Ollama 并 ollama pull qwen2.5:7b"
}

# ── 3) 后端 uvicorn ────────────────────────────────────────────────────────
if (Test-Port $BackendPort) {
    Write-Warning "端口 $BackendPort 已被占用，跳过启动后端（确认是同一个实例）。"
} else {
    $backendOut = Join-Path $tmp "backend.out.log"
    $backendErr = Join-Path $tmp "backend.err.log"
    Write-Host "==> 启动后端 127.0.0.1:$BackendPort (日志: $backendOut)"
    $backendProc = Start-Process -FilePath $python `
        -ArgumentList @("-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "$BackendPort") `
        -WorkingDirectory $RepoRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $backendOut -RedirectStandardError $backendErr
    $ready = $false
    for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 2
        if (Test-Port $BackendPort) { $ready = $true; break }
        if ($backendProc.HasExited) {
            Write-Warning "后端进程提前退出，请查看 $backendErr"
            break
        }
    }
    if ($ready) { Write-Host "==> 后端就绪 http://127.0.0.1:$BackendPort/health" }
}

# ── 4) 前端构建（产物 frontend/dist） ─────────────────────────────────────
$dist = Join-Path $RepoRoot "frontend\dist"
if (-not $SkipBuild) {
    $npm = (Get-Command npm -ErrorAction Stop).Source
    Push-Location (Join-Path $RepoRoot "frontend")
    try {
        if (-not (Test-Path (Join-Path $RepoRoot "frontend\node_modules"))) {
            Write-Host "==> npm install（首次）..."
            & $npm install --no-audit --no-fund
        }
        Write-Host "==> npm run build -> frontend/dist ..."
        & $npm run build
        if ($LASTEXITCODE -ne 0) { throw "前端构建失败 (npm run build)" }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "==> 跳过构建（-SkipBuild），使用现有 $dist"
}

# ── 5) 静态服务器 + /api 代理 ─────────────────────────────────────────────
$node = (Get-Command node -ErrorAction Stop).Source
$serverOut = Join-Path $tmp "front.out.log"
$serverErr = Join-Path $tmp "front.err.log"
Write-Host "==> 启动前端静态服务 http://127.0.0.1:$WebPort (日志: $serverOut)"
$serverScript = Join-Path $PSScriptRoot "serve-dist.mjs"
$webProc = Start-Process -FilePath $node `
    -ArgumentList @($serverScript, $dist, "--port", "$WebPort", "--backend", "http://127.0.0.1:$BackendPort") `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $serverOut -RedirectStandardError $serverErr

Start-Sleep -Seconds 2
Write-Host ""
Write-Host "=========================================================="
Write-Host "  岗位能力图谱系统（本机生产模式）"
Write-Host "  前端: http://127.0.0.1:$WebPort"
Write-Host "  后端: http://127.0.0.1:$BackendPort/docs"
Write-Host "  按 Enter 停止并清理进程 ..."
Write-Host "=========================================================="
try {
    Read-Host | Out-Null
} finally {
    if ($backendProc) { Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue }
    if ($webProc)     { Stop-Process -Id $webProc.Id -Force -ErrorAction SilentlyContinue }
    Write-Host "==> 已停止后端与前端进程"
}
