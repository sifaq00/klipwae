@echo off
title Klipwae
cd /d D:\Project\auto-clipper-app

set BACKEND_PORT=8180
set FRONTEND_PORT=5173

rem ---- Cek port: kalau Klipwae sendiri sudah jalan, skip ----
curl -s -o nul -w "%%{http_code}" http://localhost:%BACKEND_PORT%/api/health | findstr "200" >nul
if %errorlevel%==0 (
    echo [OK] Backend Klipwae sudah jalan di port %BACKEND_PORT%, skip start.
    goto :frontend
)
netstat -ano | findstr ":%BACKEND_PORT% " | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo [ERROR] Port %BACKEND_PORT% dipakai proses LAIN bukan Klipwae.
    echo         Ganti port: set BACKEND_PORT=8181 lalu jalankan ulang.
    pause
    exit /b 1
)
start "klipwae-api" /b cmd /c "cd /d D:\Project\auto-clipper-app\backend && set BACKEND_PORT=%BACKEND_PORT% && .venv\Scripts\python.exe -m uvicorn server:app --port %BACKEND_PORT% --reload"

:frontend
rem ---- Cek frontend ----
curl -s http://localhost:%FRONTEND_PORT%/ | findstr "Auto-Clipper" >nul
if %errorlevel%==0 (
    echo [OK] Frontend Klipwae sudah jalan di port %FRONTEND_PORT%, skip start.
    goto :open
)
netstat -ano | findstr ":%FRONTEND_PORT% " | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo [ERROR] Port %FRONTEND_PORT% dipakai proses LAIN bukan Klipwae.
    echo         Ganti port: set FRONTEND_PORT=5273 lalu jalankan ulang.
    pause
    exit /b 1
)
start "klipwae-ui" /b cmd /c "cd /d D:\Project\auto-clipper-app\frontend && set PORT=%FRONTEND_PORT% && npm run dev"

:open
rem Tunggu sebentar biar servis sempat boot, lalu buka browser
timeout /t 6 /nobreak >nul
start http://localhost:%FRONTEND_PORT%

echo.
echo ============================================================
echo   Klipwae Studio JALAN.
echo   Backend  : http://localhost:%BACKEND_PORT%
echo   Frontend : http://localhost:%FRONTEND_PORT%
echo.
echo   TUTUP WINDOW INI = HENTIKAN SEMUA PROSES.
echo ============================================================
echo.

:loop
timeout /t 1 /nobreak >nul
goto loop
