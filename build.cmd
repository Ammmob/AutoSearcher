@echo off
setlocal

cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_portable.ps1"
set "build_exit_code=%ERRORLEVEL%"

echo.
if "%build_exit_code%"=="0" (
    echo Build completed successfully.
) else (
    echo Build failed with exit code %build_exit_code%.
)
pause
exit /b %build_exit_code%
