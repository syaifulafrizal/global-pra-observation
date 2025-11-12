#!/bin/bash
# Daily PRA Analysis Workflow (Linux)
# Runs: pra_nighttime.py -> integrate_earthquakes.py -> upload_results.py
#
# NOTE: This script processes ALL stations from stations.json automatically.
# To process specific stations only, set INTERMAGNET_STATIONS environment variable
# before running (e.g., export INTERMAGNET_STATIONS="KAK,HER")

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Ensure we process ALL stations (unset INTERMAGNET_STATIONS if it exists)
# This ensures the script processes all stations from stations.json
if [ -n "$INTERMAGNET_STATIONS" ]; then
    unset INTERMAGNET_STATIONS
    echo "Note: INTERMAGNET_STATIONS was unset - processing ALL stations"
fi

# Create logs directory
mkdir -p logs

# Log file
LOG_FILE="logs/daily_analysis_$(date +%Y%m%d_%H%M%S).log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=========================================="
log "Starting Daily PRA Analysis Workflow"
log "=========================================="

# Step 1: Run main analysis
log "Step 1: Running PRA analysis (pra_nighttime.py)..."
python3 pra_nighttime.py >> "$LOG_FILE" 2>&1
if [ $? -ne 0 ]; then
    log "ERROR: PRA analysis failed"
    exit 1
fi
log "PRA analysis completed successfully"

# Step 2: Integrate earthquakes
log "Step 2: Integrating earthquake data (integrate_earthquakes.py)..."
python3 integrate_earthquakes.py >> "$LOG_FILE" 2>&1
if [ $? -ne 0 ]; then
    log "WARNING: Earthquake integration failed, continuing..."
else
    log "Earthquake integration completed"
fi

# Step 3: Prepare web files
log "Step 3: Preparing web files (upload_results.py)..."
python3 upload_results.py >> "$LOG_FILE" 2>&1
if [ $? -ne 0 ]; then
    log "ERROR: Web file preparation failed"
    exit 1
fi
log "Web files prepared successfully"

log "=========================================="
log "Daily workflow completed successfully!"
log "=========================================="

exit 0

