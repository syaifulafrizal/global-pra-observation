@echo off
REM Master Deployment Script - Windows Batch Version
REM Runs without input prompts so Task Scheduler can finish unattended.

echo ==========================================
echo PRA Complete Deployment Workflow
echo ==========================================
echo.

REM Run the PowerShell script
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0deploy_all.ps1"
set "workflowExit=%ERRORLEVEL%"

REM Check exit code
if %workflowExit% NEQ 0 (
    echo.
    echo ERROR: Workflow failed!
    exit /b %workflowExit%
)

echo.
echo Workflow completed successfully!
exit /b 0

