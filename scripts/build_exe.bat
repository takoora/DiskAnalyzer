@echo off
setlocal enabledelayedexpansion

set APP_NAME=DiskAnalyzer
set VERSION=%~1
if "%VERSION%"=="" set VERSION=1.0.0

set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..
set BUILD_DIR=%PROJECT_DIR%\build
set DIST_DIR=%PROJECT_DIR%\dist
set EXE_PATH=%DIST_DIR%\%APP_NAME%-%VERSION%-windows.zip

echo ==^> Building %APP_NAME% v%VERSION%

REM Clean previous builds
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
mkdir "%BUILD_DIR%"
mkdir "%DIST_DIR%"

REM Check dependencies
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: python not found
    exit /b 1
)

REM Install pyinstaller if needed
python -m PyInstaller --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ==^> Installing PyInstaller...
    pip install pyinstaller
)

REM Build the exe with PyInstaller
echo ==^> Running PyInstaller...
set ICON_FILE=%PROJECT_DIR%\resources\icons\AppIcon.ico

python -m PyInstaller ^
    --name "%APP_NAME%" ^
    --windowed ^
    --onedir ^
    --noconfirm ^
    --clean ^
    --icon "%ICON_FILE%" ^
    --distpath "%DIST_DIR%" ^
    --workpath "%BUILD_DIR%\pyinstaller" ^
    --specpath "%BUILD_DIR%" ^
    --add-data "%PROJECT_DIR%\disk_analyzer;disk_analyzer" ^
    "%PROJECT_DIR%\main.py"

if not exist "%DIST_DIR%\%APP_NAME%\%APP_NAME%.exe" (
    echo Error: exe not found
    exit /b 1
)

echo ==^> Creating zip archive...
powershell -Command "Compress-Archive -Path '%DIST_DIR%\%APP_NAME%' -DestinationPath '%EXE_PATH%' -Force"

echo.
echo ==^> Done! Archive created at:
echo     %EXE_PATH%
echo.
