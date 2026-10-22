@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 goto SETUP_ERROR
title BOT CEK STOK - RUNNING
echo.
echo ==========================================
echo  MEMULAI BOT CEK STOK...
echo  Tekan Ctrl+C untuk berhenti
echo ==========================================
echo.

python --version >nul 2>&1
if errorlevel 1 goto SETUP_ERROR
if not exist "BOT_STOK.py" goto SETUP_ERROR
if not exist "requirements.txt" goto SETUP_ERROR

:: Siapkan dependensi satu kali, bukan setiap kali bot restart.
python -m pip install -r requirements.txt
if errorlevel 1 goto SETUP_ERROR

:START
python -u BOT_STOK.py
if not errorlevel 1 goto STOPPED

echo.
echo Bot berhenti dengan error. Restart dalam 5 detik...
timeout /t 5 /nobreak >nul
goto START

:STOPPED
echo Bot dihentikan.
exit /b 0

:SETUP_ERROR
echo.
echo Persiapan gagal. Periksa Python, file bot, dan requirements.txt.
echo Jalankan install_vps.bat untuk memasang dependensi dan browser Chromium.
pause
exit /b 1
