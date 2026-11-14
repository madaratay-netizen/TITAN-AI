@echo off
REM ===== ADWIN OS — one-click launcher (Windows) =====
REM Double-click this file. It starts Ollama + ComfyUI + the ADWIN OS backend
REM and opens the dashboard in your browser. Close the minimized windows to stop.
title ADWIN OS
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_windows.ps1"
echo.
pause
