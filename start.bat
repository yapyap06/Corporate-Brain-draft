@echo off
echo ============================================
echo   Corporate Brain — Starting All Services
echo ============================================

echo.
echo [1/2] Starting Backend API (FastAPI on port 8000)...
start "Corporate Brain API" /D "%~dp0" cmd /k "C:\Users\Dell\AppData\Local\Programs\Python\Python313\python.exe -m uvicorn backend.main:app --reload --port 8000"

timeout /t 2 /nobreak >nul

echo.
echo [2/2] Starting Frontend (port 8765)...
start "Corporate Brain Frontend" /D "%~dp0\frontend" cmd /k "C:\Users\Dell\AppData\Local\Programs\Python\Python313\python.exe -m http.server 8765"

timeout /t 2 /nobreak >nul

echo.
echo ============================================
echo   Both servers are starting!
echo.
echo   Frontend:  http://localhost:8765
echo   API:       http://localhost:8000
echo   API Docs:  http://localhost:8000/docs
echo ============================================
echo.
echo Opening browser...
start http://localhost:8765

pause
