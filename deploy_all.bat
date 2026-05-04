@echo off
REM Master Deployment Script - Windows Batch Version
REM Double-click this file to run the complete workflow

echo ==========================================
echo PRA Complete Deployment Workflow
echo ==========================================
echo.

REM Run the PowerShell script
powershell.exe -ExecutionPolicy Bypass -File "%~dp0deploy_all.ps1"

REM Check exit code
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Workflow failed!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Workflow completed successfully!
pause

