@echo off
title WMS Dev
cd /d "%~dp0"

set BACKEND_PORT=8912
set FRONTEND_PORT=5173

:: ---------- fix Python PATH (Windows Store stub takes priority) ----------
set "REAL_PYTHON=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe"
if not exist "%REAL_PYTHON%" (
    set "REAL_PYTHON=C:\Program Files\Python311\python.exe"
)
if not exist "%REAL_PYTHON%" (
    echo [ERROR] Python 3.11 not found. Checked:
    echo   C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe
    echo   C:\Program Files\Python311\python.exe
    pause
    exit /b 1
)

set "PATH=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311;C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\Scripts;%PATH%"

:: ---------- route ----------
if /I "%1"=="stop"    goto :stop
if /I "%1"=="restart" goto :restart
if /I "%1"=="status"  goto :status

:: ============================ Start ============================
:start
echo ============================================================
echo   WMS RAG V2 Dev
echo ============================================================
echo   Python: %REAL_PYTHON%
%REAL_PYTHON% --version
echo   Ports:  backend=%BACKEND_PORT%  frontend=%FRONTEND_PORT%
echo.

echo [1/2] Starting backend on :%BACKEND_PORT% ...
start "WMS-Backend" cmd /c "title WMS-Backend :%BACKEND_PORT% && cd /d %~dp0backend && %REAL_PYTHON% -m uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT% --reload && pause"

echo [2/2] Starting frontend on :%FRONTEND_PORT% ...
start "WMS-Frontend" cmd /c "title WMS-Frontend :%FRONTEND_PORT% && cd /d %~dp0frontend\vue-app && npm run dev && pause"

echo.
echo ============================================================
echo   Frontend : http://localhost:%FRONTEND_PORT%
echo   Backend  : http://localhost:%BACKEND_PORT%
echo   API      : http://localhost:%BACKEND_PORT%/api/v1
echo ============================================================
echo.
echo   start.bat stop    -- stop all
echo   start.bat restart -- restart all
echo   start.bat status  -- show status
echo.
pause
exit /b 0

:: ============================ Stop ============================
:stop
echo Stopping services on ports %BACKEND_PORT% / %FRONTEND_PORT% ...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%BACKEND_PORT% " ^| findstr "LISTENING" 2^>nul') do (
    echo   kill :%BACKEND_PORT% PID=%%a
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%FRONTEND_PORT% " ^| findstr "LISTENING" 2^>nul') do (
    echo   kill :%FRONTEND_PORT% PID=%%a
    taskkill /PID %%a /F >nul 2>&1
)
taskkill /FI "WINDOWTITLE eq WMS-Backend*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq WMS-Frontend*" /F >nul 2>&1

echo Done.
pause
exit /b 0

:: ============================ Restart ============================
:restart
call "%~dp0start.bat" stop
timeout /t 2 >nul
call "%~dp0start.bat" start
exit /b 0

:: ============================ Status ============================
:status
echo Backend  :%BACKEND_PORT% ...
curl -s -o NUL http://localhost:%BACKEND_PORT%/health 2>nul && echo   OK || echo   DOWN
echo Frontend :%FRONTEND_PORT% ...
curl -s -o NUL http://localhost:%FRONTEND_PORT% 2>nul && echo   OK || echo   DOWN
pause
exit /b 0
