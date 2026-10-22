@echo off
title BOT CEK STOK - RUNNING
echo.
echo ==========================================
echo  MEMULAI BOT CEK STOK...
echo  (Tekan Ctrl+C untuk berhenti)
echo ==========================================
echo.

:START
python -m pip install aiohttp playwright requests python-dotenv >nul 2>&1
python BOT_STOK.py

echo.
echo ⚠️ Bot berhenti/crash.
echo Restarting dalam 5 detik...
timeout /t 5
echo Restarting...
goto START
