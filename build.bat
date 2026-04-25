@echo off
REM Cross-platform build script for LLM-ROUTE (Windows)
REM Usage: build.bat [--clean] [--debug]

setlocal enabledelayedexpansion

set "CLEAN_FLAG=--clean"
set "DEBUG_FLAG="

REM Parse arguments
:parse_args
if "%~1"=="" goto :done_args
if /i "%~1"=="--clean" goto :next_arg
if /i "%~1"=="--debug" set "DEBUG_FLAG=--debug" & goto :next_arg
if /i "%~1"=="-h" goto :show_help
if /i "%~1"=="--help" goto :show_help
echo Unknown parameter: %~1
exit /b 1

:next_arg
shift
goto :parse_args

:show_help
echo Usage: build.bat [OPTIONS]
echo.
echo Options:
echo   --clean    Clean build (default behavior)
echo   --debug    Build with debug information
echo   -h, --help Show this help message
exit /b 0

:done_args

echo ============================================
echo Building LLM-ROUTE for Windows...
echo ============================================
echo.

REM Check PyInstaller
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller not found, installing...
    pip install pyinstaller
)

REM Check for icon file
if not exist "icon.ico" (
    echo Warning: icon.ico not found. The executable will use default icon.
)

REM Run PyInstaller
echo Running PyInstaller...
pyinstaller build.spec %CLEAN_FLAG% %DEBUG_FLAG%
if errorlevel 1 (
    echo.
    echo Build FAILED!
    pause
    exit /b 1
)

echo.
echo ============================================
echo Build complete!
echo Executable: dist\llm-route.exe
echo ============================================
echo.
pause
