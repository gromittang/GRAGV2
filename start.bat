@echo off
setlocal
title WMS RAG V2 - Dev Launcher
cd /d "%~dp0"

:: ============================================================
::  Config
:: ============================================================
set BACKEND_PORT=8912
set FRONTEND_PORT=5173
set BACKEND_TITLE=WMS-Backend
set FRONTEND_TITLE=WMS-Frontend

:: ============================================================
::  Fix Python PATH
:: ============================================================
set "PYTHON311_A=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe"
set "PYTHON311_B=C:\Program Files\Python311\python.exe"
if exist "%PYTHON311_A%" (
    set "REAL_PYTHON=%PYTHON311_A%"
) else if exist "%PYTHON311_B%" (
    set "REAL_PYTHON=%PYTHON311_B%"
) else (
    echo [ERROR] Python 3.11 not found.
    echo Checked: "%PYTHON311_A%"
    echo Checked: "%PYTHON311_B%"
    pause
    exit /b 1
)
set "PATH=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311;C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\Scripts;%PATH%"

:: ============================================================
::  CLI mode (backward compatible)
:: ============================================================
if /I "%~1"=="stop"    goto :svc_stop_all
if /I "%~1"=="restart" goto :svc_restart_all
if /I "%~1"=="status"  goto :svc_status
if /I "%~1"=="start"   goto :svc_start_all

:: ============================================================
::  INTERACTIVE MENU
:: ============================================================
:menu
cls
call :draw_menu
set "OPT="
set /p "OPT=  >> Choose [1-5 / S / B / F / Q]: "
if /I "%OPT%"=="1"  goto :svc_start_all
if /I "%OPT%"=="2"  goto :svc_stop_all
if /I "%OPT%"=="3"  goto :svc_restart_all
if /I "%OPT%"=="4"  goto :svc_restart_backend
if /I "%OPT%"=="5"  goto :svc_restart_frontend
if /I "%OPT%"=="s"  goto :svc_status
if /I "%OPT%"=="b"  goto :open_backend
if /I "%OPT%"=="f"  goto :open_frontend
if /I "%OPT%"=="q"  goto :quit
goto :menu

:: ============================================================
::  Menu drawing
:: ============================================================
:draw_menu
echo.
echo   ========================================================
echo          WMS RAG V2  -  Dev Launcher
echo   ========================================================
echo     Backend  :%BACKEND_PORT%  ^|  Frontend  :%FRONTEND_PORT%
echo   --------------------------------------------------------
call :draw_backend_status
call :draw_frontend_status
echo   --------------------------------------------------------
echo.
echo     [1] Start All
echo     [2] Stop All
echo     [3] Restart All
echo     ------------------------
echo     [4] Restart Backend Only
echo     [5] Restart Frontend Only
echo     ------------------------
echo     [S] Show Status
echo     [B] Open Backend API docs
echo     [F] Open Frontend
echo     [Q] Quit
echo   ========================================================
exit /b

:draw_backend_status
netstat -ano 2>nul | find ":%BACKEND_PORT%" | find "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo     Backend  : STOPPED
) else (
    echo     Backend  : RUNNING
)
exit /b

:draw_frontend_status
netstat -ano 2>nul | find ":%FRONTEND_PORT%" | find "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo     Frontend : STOPPED
) else (
    echo     Frontend : RUNNING
)
exit /b

:: ============================================================
::  Start All
:: ============================================================
:svc_start_all
cls
echo.
echo   >> Starting services ...
call :svc_start_backend
call :svc_start_frontend
echo.
echo   >> Done:
echo      Frontend : http://localhost:%FRONTEND_PORT%
echo      Backend  : http://localhost:%BACKEND_PORT%
echo      API docs : http://localhost:%BACKEND_PORT%/docs
echo.
pause
goto :menu

:: ============================================================
::  Stop All
:: ============================================================
:svc_stop_all
cls
echo.
echo   >> Stopping all services ...
call :svc_stop_backend
call :svc_stop_frontend
echo   >> Done.
echo.
pause
goto :menu

:: ============================================================
::  Restart All
:: ============================================================
:svc_restart_all
cls
echo   >> Restarting all services ...
call :svc_stop_backend
call :svc_stop_frontend
timeout /t 2 >nul 2>&1
call :svc_start_backend
call :svc_start_frontend
echo   >> Restart complete.
echo.
pause
goto :menu

:: ============================================================
::  Restart Backend
:: ============================================================
:svc_restart_backend
cls
echo   >> Restarting backend ...
call :svc_stop_backend
timeout /t 2 >nul 2>&1
call :svc_start_backend
echo   >> Backend restarted.
echo.
pause
goto :menu

:: ============================================================
::  Restart Frontend
:: ============================================================
:svc_restart_frontend
cls
echo   >> Restarting frontend ...
call :svc_stop_frontend
timeout /t 2 >nul 2>&1
call :svc_start_frontend
echo   >> Frontend restarted.
echo.
pause
goto :menu

:: ============================================================
::  Status
:: ============================================================
:svc_status
cls
echo.
echo   ========================================================
echo     Service Status
echo   ========================================================
echo.
echo     Backend  :%BACKEND_PORT%
netstat -ano 2>nul | find ":%BACKEND_PORT%" | find "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo       Status: DOWN
) else (
    echo       Status: RUNNING
    curl -s http://localhost:%BACKEND_PORT%/health 2>nul | find "ok" >nul 2>&1 && echo       Health: OK || echo       Health: --
)
echo.
echo     Frontend :%FRONTEND_PORT%
netstat -ano 2>nul | find ":%FRONTEND_PORT%" | find "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo       Status: DOWN
) else (
    echo       Status: RUNNING
)
echo.
echo   ========================================================
echo.
pause
goto :menu

:: ============================================================
::  Browser
:: ============================================================
:open_backend
start http://localhost:%BACKEND_PORT%/docs
goto :menu

:open_frontend
start http://localhost:%FRONTEND_PORT%
goto :menu

:: ============================================================
::  Quit
:: ============================================================
:quit
cls
echo.
echo   ========================================================
echo     Launcher closed.
echo     Services keep running in background windows.
echo     Use "start.bat stop" to kill all services.
echo   ========================================================
echo.
exit /b 0

:: ============================================================
::  Service: start backend
:: ============================================================
:svc_start_backend
netstat -ano 2>nul | find ":%BACKEND_PORT%" | find "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo     Backend already running on :%BACKEND_PORT%, skip.
    exit /b
)
echo     Starting backend on :%BACKEND_PORT% ...
start "%BACKEND_TITLE%" cmd /c "title %BACKEND_TITLE% :%BACKEND_PORT% && cd /d %~dp0backend && %REAL_PYTHON% -m uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT% --reload"
exit /b

:: ============================================================
::  Service: start frontend
:: ============================================================
:svc_start_frontend
netstat -ano 2>nul | find ":%FRONTEND_PORT%" | find "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo     Frontend already running on :%FRONTEND_PORT%, skip.
    exit /b
)
echo     Starting frontend on :%FRONTEND_PORT% ...
start "%FRONTEND_TITLE%" cmd /c "title %FRONTEND_TITLE% :%FRONTEND_PORT% && cd /d %~dp0frontend\vue-app && npm run dev"
exit /b

:: ============================================================
::  Service: stop backend
:: ============================================================
:svc_stop_backend
echo     Stopping backend on :%BACKEND_PORT% ...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find ":%BACKEND_PORT%" ^| find "LISTENING"') do (
    echo       kill PID=%%a
    taskkill /PID %%a /F >nul 2>&1
)
taskkill /FI "WINDOWTITLE eq %BACKEND_TITLE%*" /F >nul 2>&1
exit /b

:: ============================================================
::  Service: stop frontend
:: ============================================================
:svc_stop_frontend
echo     Stopping frontend on :%FRONTEND_PORT% ...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find ":%FRONTEND_PORT%" ^| find "LISTENING"') do (
    echo       kill PID=%%a
    taskkill /PID %%a /F >nul 2>&1
)
taskkill /FI "WINDOWTITLE eq %FRONTEND_TITLE%*" /F >nul 2>&1
exit /b
