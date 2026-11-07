# AI 智能伴侣（FastAPI :8001 + Streamlit :8511） · Windows 一键启动（默认本地 Ollama；DeepSeek 通过 MODEL_PROVIDER=deepseek 切换备选）
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = "python"
if (-not (Test-Path $py)) { $py = "python" }

function Test-Port([int]$p) { [bool](Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue) }

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "已从 .env.example 生成 .env（默认 ollama 模式）" -ForegroundColor Yellow
}



if (Test-Port 8001) {
    Write-Host "后端端口 8001 已被占用，视为已在运行，跳过启动" -ForegroundColor Yellow
} else {
    Write-Host "启动 FastAPI 后端（http://localhost:8001）..." -ForegroundColor Cyan
    $env:PYTHONPATH = "."
    $backend = Start-Process -FilePath $py -ArgumentList -m uvicorn backend.main:app --port 8001 -PassThru -WindowStyle Minimized
    Start-Sleep -Seconds 6
    if (-not (Test-Port 8001)) {
        Write-Host "后端启动失败（端口 8001 未监听），请查看日志" -ForegroundColor Red
    }
}

if (Test-Port 8511) {
    Write-Host "前端端口 8511 已被占用，视为已在运行，跳过启动（http://localhost:8511）" -ForegroundColor Yellow
    Read-Host "按回车结束"
    if ($backend) { Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue }
    exit 0
}
Write-Host "启动 Streamlit 前端（http://localhost:8511）..." -ForegroundColor Cyan
try {
    & $py -m streamlit run app\main.py --server.port 8511 --server.headless true
} finally {
    if ($backend) { Write-Host "关闭前端，同时停止后端 PID=$($backend.Id)..." -ForegroundColor Yellow; Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue }
}