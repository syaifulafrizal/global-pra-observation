@echo off
REM Daily PRA Analysis Workflow (Batch version)
REM For Windows Task Scheduler

cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -File "%~dp0run_daily_analysis.ps1"

