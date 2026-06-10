@echo off
echo ============================================
echo  RouteScope - Frontend (React + Vite)
echo ============================================
cd /d "%~dp0frontend"

echo Installing npm dependencies...
call npm install

echo.
echo Starting Vite dev server on http://localhost:5173
echo.
call npm run dev
pause
