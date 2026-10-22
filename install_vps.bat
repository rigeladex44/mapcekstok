@echo off
setlocal EnableDelayedExpansion
title Installer BOT CEK STOK (VPS Edition)

echo ===================================================
echo   BOT CEK STOK - VPS AUTO INSTALLER
echo   (Python + Visual C++ + Dependencies)
echo ===================================================
echo.

:: 1. Cek Koneksi Internet
echo [1/6] Cek Koneksi Internet...
ping -n 1 8.8.8.8 >nul
if %errorlevel% neq 0 (
    echo    ⚠️ Tidak ada koneksi internet! Harap sambungkan internet.
    pause
    exit
)
echo    ✅ Internet OK.

:: 2. Cek Visual C++ Redistributable (Solusi Error DLL)
echo.
echo [2/6] Memeriksa Visual C++ Redistributable...
:: Cek registry key umum untuk VC Redist 2015-2022
reg query "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" >nul 2>&1
if %errorlevel% neq 0 (
    echo    ⚠️ Visual C++ Redistributable belum terinstall.
    echo    DLL Greenlet/Playwright butuh ini. Sedang mendownload...
    
    curl -L -o vc_redist.x64.exe https://aka.ms/vs/17/release/vc_redist.x64.exe
    
    echo    ⏳ Menginstall Visual C++ Redistributable...
    echo    (Jendela installer mungkin muncul, harap tunggu...)
    
    :: Install Silent /Passive /NoRestart
    vc_redist.x64.exe /install /passive /norestart
    
    echo    ✅ Visual C++ selesai diinstall.
    del vc_redist.x64.exe
) else (
    echo    ✅ Visual C++ Redistributable sudah ada.
)

:: 3. Cek Python
echo.
echo [3/6] Memeriksa Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo    ⚠️ Python tidak terdeteksi.
    echo    ⏳ Sedang mendownload Python 3.11...
    
    curl -o python_installer.exe https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
    
    echo    ⏳ Menginstall Python...
    python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
    
    del python_installer.exe
    
    echo    ✅ Python berhasil diinstall!
    echo    ⚠️ PENTING: Mohon TUTUP jendela ini dan JALANKAN LAGI agar path Python terdeteksi.
    pause
    exit
) else (
    echo    ✅ Python sudah terinstall.
)

:: 4. Update PIP & clean cache
echo.
echo [4/6] Menyiapkan PIP...
python -m pip install --upgrade pip
:: Uninstall clean jika dipaksa user? Tidak perlu default.

:: 5. Install Dependencies
echo.
echo [5/6] Menginstall Library Python...
python -m pip install --upgrade setuptools wheel
:: No-cache-dir untuk menghindari file corrupt di cache
python -m pip install --no-cache-dir -r requirements.txt
python -m pip install --no-cache-dir requests python-dotenv playwright aiohttp

:: 6. Install Browser
echo.
echo [6/6] Menginstall Browser...
python -m playwright install chromium

echo.
echo ===================================================
echo    🎉 INSTALASI SIAP!
echo ===================================================
echo.
echo Jalankan bot dengan membuka file: run_bot_vps.bat
echo.
pause
