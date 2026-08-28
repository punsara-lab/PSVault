@echo off
echo ========================================
echo   PSVault Build Script
echo   Developer: punsara
echo ========================================
echo.

echo [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ and add to PATH.
    pause
    exit /b 1
)
python --version
echo.

echo [2/4] Installing dependencies...
python -m pip install --upgrade pip 2>nul
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install requirements.
    pause
    exit /b 1
)
python -m pip install pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller.
    pause
    exit /b 1
)
echo.

echo [3/4] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist PSVault.spec del /q PSVault.spec
echo.

echo [4/4] Building PSVault.exe...
python -m PyInstaller --onefile --windowed --uac-admin --name PSVault ^
    --collect-all customtkinter ^
    --hidden-import cryptography ^
    app.py
if errorlevel 1 (
    echo ERROR: Build failed.
    pause
    exit /b 1
)
echo.

echo ========================================
echo   BUILD SUCCESS!
echo   Output: dist\PSVault.exe
echo ========================================
pause
