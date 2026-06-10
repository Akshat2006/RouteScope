@echo off
echo ============================================
echo  RouteScope - Backend (FastAPI) - Port 8000
echo ============================================

if not exist "backend\.venv" (
    echo Creating virtual environment...
    python -m venv backend\.venv
)

echo Installing dependencies...
backend\.venv\Scripts\pip install -r backend\requirements.txt --quiet

echo.
echo Starting FastAPI server on http://localhost:8000
echo Swagger UI: http://localhost:8000/docs
echo.
backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
pause
