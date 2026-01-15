@echo off
REM Script to initialize 7-day dataset and rerun analysis
REM This downloads last 7 days of data, processes them, and sets up the rolling window

echo ==========================================
echo PRA Analysis - Initialize 7-Day Dataset
echo ==========================================
echo.
echo This will:
echo   1. Download last 7 days of geomagnetic field data (10/11 to today)
echo   2. Process each day to build the historical dataset
echo   3. Download and process last 7 days of earthquake data
echo   4. Set up rolling 7-day window (oldest day deleted when new day added)
echo.
echo Note: Existing analysis results will be deleted and reprocessed.
echo.
pause

echo.
echo Step 1: Deleting existing analysis results...
for /d %%d in (INTERMAGNET_DOWNLOADS\*) do (
    if exist "%%d\PRA_Night_*.json" (
        del /q "%%d\PRA_Night_*.json"
        echo Deleted results in %%d
    )
)

echo.
echo ==========================================
echo Step 2: Downloading and processing 7-day dataset...
echo ==========================================
echo.

set FORCE_RERUN=1
REM Try to use Anaconda Python first, fallback to py launcher, then python
if exist "C:\Users\SYAIFUL\anaconda3\python.exe" (
    "C:\Users\SYAIFUL\anaconda3\python.exe" initialize_7day_dataset.py
    if errorlevel 1 (
        echo WARNING: Initialization script had errors, running standard analysis as fallback...
        "C:\Users\SYAIFUL\anaconda3\python.exe" pra_nighttime.py
    )
) else (
    py -3.9 initialize_7day_dataset.py
    if errorlevel 1 (
        python initialize_7day_dataset.py
        if errorlevel 1 (
            echo WARNING: Initialization script had errors, running standard analysis as fallback...
            python pra_nighttime.py
        )
    )
)

echo.
echo ==========================================
echo Step 3: Processing earthquake data...
echo ==========================================
echo.

if exist "C:\Users\SYAIFUL\anaconda3\python.exe" (
    "C:\Users\SYAIFUL\anaconda3\python.exe" integrate_earthquakes.py
) else (
    py -3.9 integrate_earthquakes.py
    if errorlevel 1 (
        python integrate_earthquakes.py
    )
)

echo.
echo ==========================================
echo 7-Day Dataset Initialization Complete!
echo ==========================================
echo.
echo Summary:
echo   - Last 7 days of data have been downloaded and processed
echo   - Historical dataset is ready for EVT threshold calculation
echo   - Rolling window is set up (oldest day will be deleted when new day is added)
echo.
echo Next steps:
echo   - Run deploy_all.bat to deploy the results
echo   - Future daily runs will automatically maintain the 7-day window
echo.
pause

