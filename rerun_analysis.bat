@echo off
REM Quick script to rerun analysis for all stations
REM This deletes existing JSON results to force reprocessing

echo ==========================================
echo PRA Analysis Rerun Script
echo ==========================================
echo.
echo This will delete existing analysis results and rerun for all stations.
echo.
pause

echo.
echo Deleting existing analysis results...
for /d %%d in (INTERMAGNET_DOWNLOADS\*) do (
    if exist "%%d\PRA_Night_*.json" (
        del /q "%%d\PRA_Night_*.json"
        echo Deleted results in %%d
    )
)

echo.
echo ==========================================
echo Starting analysis with FORCE_RERUN enabled...
echo ==========================================
echo.

set FORCE_RERUN=1
REM Try to use Anaconda Python first, fallback to py launcher, then python
if exist "C:\Users\SYAIFUL\anaconda3\python.exe" (
    "C:\Users\SYAIFUL\anaconda3\python.exe" pra_nighttime.py
) else (
    py -3.9 pra_nighttime.py
    if errorlevel 1 (
        python pra_nighttime.py
    )
)

echo.
echo ==========================================
echo Analysis complete!
echo ==========================================
pause

