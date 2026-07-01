@echo off
echo =============================================
echo  AI Agent MVP - Starting Dev Servers
echo =============================================
echo.
echo [1] FastAPI backend  -> http://localhost:8000
echo [2] Next.js frontend -> http://localhost:3000
echo.

start "FastAPI Backend" cmd /k "cd /d C:\MCNA\P95-Duan_congty_maymac\ai_agent_mvp && uvicorn backend.api.main:app --reload --port 8000"
timeout /t 2 /nobreak >nul
start "Next.js Frontend" cmd /k "cd /d C:\MCNA\P95-Duan_congty_maymac\ai_agent_mvp\frontend && npm run dev"

echo.
echo Both servers starting...
echo Open http://localhost:3000 in your browser.
