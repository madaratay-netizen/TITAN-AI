# ADWIN OS - Windows launcher.
# Starts everything ADWIN needs (Ollama + ComfyUI + backend) and opens the
# dashboard in your browser. Safe to run repeatedly: it skips whatever is
# already running. Nothing here touches disks or system settings.

$ErrorActionPreference = "Continue"
$ROOT   = Split-Path -Parent $PSScriptRoot
$VENV   = Join-Path $ROOT ".venv\Scripts\python.exe"
$COMFY  = Join-Path (Split-Path -Parent $ROOT) "ComfyUI"
$OLLAMA = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"

function Up($url){ try{ Invoke-RestMethod $url -TimeoutSec 2 | Out-Null; $true }catch{ $false } }

Write-Host ""
Write-Host "  ===== ADWIN OS =====" -ForegroundColor Cyan
Write-Host "  Portable offline AI workstation" -ForegroundColor DarkCyan
Write-Host ""

if (-not (Test-Path $VENV)) {
  Write-Host "[X] Python environment not found (.venv)." -ForegroundColor Red
  Write-Host "    First-time setup:  python -m venv .venv ; .\.venv\Scripts\pip install -r requirements.txt"
  Read-Host "Press Enter to exit"; exit 1
}

# 1) Ollama (local AI runtime: chat, RAG, scene planning)
if (Up "http://127.0.0.1:11434/api/version") { Write-Host "[OK] Ollama already running" -ForegroundColor Green }
elseif (Test-Path $OLLAMA) { Write-Host "[..] Starting Ollama..."; Start-Process -FilePath $OLLAMA -ArgumentList "serve" -WindowStyle Hidden }
else { Write-Host "[!] Ollama not found. Chat/RAG need it. Get it from https://ollama.com" -ForegroundColor Yellow }

# 2) ComfyUI (image generation) - optional
if (Up "http://127.0.0.1:8188/system_stats") { Write-Host "[OK] ComfyUI already running" -ForegroundColor Green }
elseif (Test-Path (Join-Path $COMFY "main.py")) {
  Write-Host "[..] Starting ComfyUI (images)..."
  Start-Process -FilePath (Join-Path $COMFY "venv\Scripts\python.exe") -ArgumentList "main.py","--lowvram","--port","8188" -WorkingDirectory $COMFY -WindowStyle Minimized
} else { Write-Host "[i] ComfyUI not installed. Image generation is optional and will be disabled." -ForegroundColor DarkGray }

# 3) ADWIN OS backend + dashboard
if (Up "http://127.0.0.1:8077/api/health") { Write-Host "[OK] ADWIN backend already running" -ForegroundColor Green }
else {
  Write-Host "[..] Starting ADWIN OS..."
  Start-Process -FilePath $VENV -ArgumentList "-m","uvicorn","backend.app.main:app","--host","127.0.0.1","--port","8077" -WorkingDirectory $ROOT -WindowStyle Minimized
}

# 4) Wait, then open the dashboard
Write-Host "[..] Waiting for ADWIN OS to be ready..."
$ok = $false
for ($i=0; $i -lt 40; $i++){ if (Up "http://127.0.0.1:8077/api/health"){ $ok=$true; break }; Start-Sleep 1 }
Write-Host ""
if ($ok) {
  Write-Host "  ADWIN OS is ready! Opening the dashboard..." -ForegroundColor Green
  Start-Process "http://127.0.0.1:8077"
} else {
  Write-Host "  Backend did not start in time. Check the minimized windows for errors." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  Dashboard:  http://127.0.0.1:8077"
Write-Host "  To STOP ADWIN OS: close the minimized 'python' windows (ADWIN / ComfyUI)."
Write-Host ""
