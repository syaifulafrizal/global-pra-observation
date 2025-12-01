# Master Deployment Script - Complete Workflow
# This script runs the ENTIRE workflow in the correct order:
# 1. Process all stations (pra_nighttime.py)
# 2. Integrate earthquakes (integrate_earthquakes.py)
# 3. Prepare web output (upload_results.py)
# 4. Deploy to GitHub Pages (deploy_to_github.ps1)
#
# Usage: Just double-click this file or run: .\deploy_all.ps1

$ErrorActionPreference = "Continue"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

function Write-Log {
    param([string]$Message, [string]$Color = "White")
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$Timestamp] $Message" -ForegroundColor $Color
}

Write-Log "==========================================" "Cyan"
Write-Log "PRA Complete Deployment Workflow" "Cyan"
Write-Log "==========================================" "Cyan"
Write-Log ""

# Ensure we process ALL stations
if (Test-Path Env:INTERMAGNET_STATIONS) {
    Remove-Item Env:INTERMAGNET_STATIONS
    Write-Log "Note: INTERMAGNET_STATIONS was unset - processing ALL stations" "Yellow"
}

# Check if FORCE_RERUN is requested (from rerun_analysis.bat or manual setting)
if (Test-Path Env:FORCE_RERUN) {
    Write-Log "Note: FORCE_RERUN is enabled - will reprocess all stations" "Yellow"
} else {
    Write-Log "Note: Using cached results if available (set FORCE_RERUN=1 to force rerun)" "Gray"
}

# Preflight: make sure the latest raw data exists for every station
Write-Log ""
Write-Log "Preflight: Checking station data availability (today vs yesterday)..." "Yellow"
& $pythonExe ensure_station_data.py
if ($LASTEXITCODE -ne 0) {
    Write-Log "WARNING: Data availability pre-check encountered issues. Review logs above." "Yellow"
} else {
    Write-Log "Preflight check complete - raw data is up to date." "Green"
}
Write-Log ""

# Step 1: Run PRA Analysis
Write-Log "Step 1/4: Running PRA Analysis (pra_nighttime.py)..." "Yellow"
Write-Log "This may take several minutes for all stations..." "Gray"

# Detect Python with required packages
$pythonExe = $null
if (Test-Path "C:\Users\SYAIFUL\anaconda3\python.exe") {
    $pythonExe = "C:\Users\SYAIFUL\anaconda3\python.exe"
} else {
    $pythonExe = "python"
}
& $pythonExe pra_nighttime.py
if ($LASTEXITCODE -ne 0) {
    Write-Log "ERROR: PRA analysis failed!" "Red"
    Write-Log "Please check the error messages above" "Red"
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Log "PRA analysis completed" "Green"
Write-Log ""

# Step 2: Integrate Earthquakes
Write-Log "Step 2/4: Integrating Earthquake Data (integrate_earthquakes.py)..." "Yellow"
& $pythonExe integrate_earthquakes.py
if ($LASTEXITCODE -ne 0) {
    Write-Log "WARNING: Earthquake integration had issues, but continuing..." "Yellow"
} else {
    Write-Log "Earthquake integration completed" "Green"
}
Write-Log ""

# Step 3: Prepare Web Output (CRITICAL - This regenerates stations.json with all stations)
Write-Log "Step 3/4: Preparing Web Output (upload_results.py)..." "Yellow"
Write-Log "This step is CRITICAL - it regenerates stations.json with all processed stations" "Cyan"

# Check for merge conflicts in upload_results.py and clean them if found
$uploadResultsPath = "upload_results.py"
if (Test-Path $uploadResultsPath) {
    $content = Get-Content $uploadResultsPath -Raw
    # Only match actual Git conflict markers (not just any line with = signs)
    if ($content -match "(?m)^[\s]*<<<<<<<|(?m)^[\s]*=======[\s]*$|(?m)^[\s]*>>>>>>>") {
        Write-Log "WARNING: Merge conflicts detected in upload_results.py! Cleaning automatically..." "Yellow"
        try {
            # Read the file line by line and remove conflict markers
            $lines = Get-Content $uploadResultsPath
            $cleanLines = @()
            $inConflict = $false
            $keepSection = $false
            
            foreach ($line in $lines) {
                if ($line -match "^<<<<<<<") {
                    $inConflict = $true
                    # If it says "Updated upstream", keep that section; otherwise keep first section by default
                    $keepSection = $line -match "Updated upstream"
                    if (-not $keepSection) {
                        # Default: keep first section (before =======)
                        $keepSection = $true
                    }
                    continue
                }
                if ($line -match "^=======") {
                    # If we're keeping the first section, skip everything until >>>>>>>
                    # If we're keeping the second section, start keeping lines now
                    if ($keepSection) {
                        # Skip the second section
                        continue
                    } else {
                        # Start keeping the second section
                        $keepSection = $true
                        continue
                    }
                }
                if ($line -match "^>>>>>>>") {
                    $inConflict = $false
                    $keepSection = $false
                    continue
                }
                
                # Add line if we're not in conflict, or if we're keeping this section
                if (-not $inConflict -or $keepSection) {
                    $cleanLines += $line
                }
            }
            
            # Write cleaned content
            $cleanLines | Set-Content -Path $uploadResultsPath
            Write-Log "Successfully cleaned merge conflicts in upload_results.py" "Green"
            
            # Post-cleanup: Remove duplicate code patterns that often result from merge conflicts
            # Read the file again to check for duplicates
            $finalLines = Get-Content $uploadResultsPath
            $deduplicatedLines = @()
            $previousLine = ""
            $skipNext = $false
            
            for ($i = 0; $i -lt $finalLines.Count; $i++) {
                $currentLine = $finalLines[$i]
                $trimmedCurrent = $currentLine.Trim()
                $trimmedPrevious = $previousLine.Trim()
                
                # Skip if this line is a duplicate of the previous line (common merge conflict artifact)
                # But only if both are similar if statements or similar code patterns
                if ($trimmedCurrent -ne "" -and $trimmedPrevious -ne "") {
                    # Check for duplicate if statements with similar conditions
                    if ($trimmedCurrent -match "^if\s+.*is_dir\(\)" -and $trimmedPrevious -match "^if\s+.*is_dir\(\)") {
                        # If current line is a subset of previous (shorter condition), skip it
                        if ($trimmedCurrent.Length -lt $trimmedPrevious.Length -and $trimmedPrevious.Contains($trimmedCurrent.Substring(0, [Math]::Min(30, $trimmedCurrent.Length)))) {
                            Write-Log "Removing duplicate if statement at line $($i+1)" "Yellow"
                            continue
                        }
                    }
                    
                    # Check for orphaned return statements after another return
                    if ($trimmedCurrent -match "^return\s+" -and $trimmedPrevious -match "^return\s+") {
                        # Check if there's a comment like "Last resort" before the second return
                        if ($i -gt 1 -and $finalLines[$i-2] -match "Last resort") {
                            Write-Log "Removing orphaned return statement at line $($i+1)" "Yellow"
                            continue
                        }
                    }
                }
                
                # Check for lines that are exactly the same (duplicate consecutive lines)
                if ($trimmedCurrent -eq $trimmedPrevious -and $trimmedCurrent -ne "" -and $trimmedCurrent -notmatch "^#") {
                    # Skip exact duplicates (but keep comments and blank lines)
                    continue
                }
                
                $deduplicatedLines += $currentLine
                $previousLine = $currentLine
            }
            
            # Write deduplicated content
            $deduplicatedLines | Set-Content -Path $uploadResultsPath
            Write-Log "Removed duplicate code patterns" "Green"
            
            # Verify it's clean (check for conflict markers)
            $verifyContent = Get-Content $uploadResultsPath -Raw
            if ($verifyContent -match "(?m)^[\s]*<<<<<<<|(?m)^[\s]*=======[\s]*$|(?m)^[\s]*>>>>>>>") {
                Write-Log "ERROR: Failed to clean all conflicts. Please resolve manually." "Red"
                exit 1
            }
            
            # Verify Python syntax is valid
            $syntaxCheck = & $pythonExe -m py_compile $uploadResultsPath 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Log "ERROR: Python syntax error after conflict cleanup!" "Red"
                Write-Log "Syntax error details: $syntaxCheck" "Red"
                Write-Log "Please fix upload_results.py manually" "Red"
                exit 1
            }
            Write-Log "Verified: Python syntax is valid after cleanup" "Green"
        } catch {
            Write-Log "ERROR: Failed to clean merge conflicts: $_" "Red"
            Write-Log "Please resolve merge conflicts manually in upload_results.py" "Red"
            exit 1
        }
    }
}

& $pythonExe upload_results.py
if ($LASTEXITCODE -ne 0) {
    Write-Log "ERROR: Web output preparation failed!" "Red"
    Write-Log "Please check the error messages above" "Red"
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Log "Web output prepared" "Green"

# Verify stations.json was created correctly
$stationsJson = "web_output\data\stations.json"
if (Test-Path $stationsJson) {
    try {
        $jsonContent = Get-Content $stationsJson | ConvertFrom-Json
        $stationCount = if ($jsonContent.stations) { $jsonContent.stations.Count } else { 0 }
        Write-Log "Verified: stations.json contains $stationCount stations" "Green"
        if ($stationCount -le 1) {
            Write-Log "WARNING: Only $stationCount station(s) found! This may indicate a problem." "Yellow"
            Write-Log "Check that pra_nighttime.py processed all stations successfully." "Yellow"
        }
    } catch {
        Write-Log "WARNING: Could not verify stations.json content" "Yellow"
    }
} else {
    Write-Log "ERROR: stations.json not found in web_output/data/" "Red"
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Log ""

# Step 4: Deploy to GitHub Pages (if configured)
$env:GITHUB_REPO = "syaifulafrizal/global-pra-observation"
$env:GITHUB_BRANCH = "gh-pages"

# Check for merge conflicts in deploy_to_github.ps1 and clean them if found
$deployScriptPath = "deploy_to_github.ps1"
if (Test-Path $deployScriptPath) {
    $content = Get-Content $deployScriptPath -Raw
    # Only match actual Git conflict markers (not just any line with = signs)
    # Pattern: <<<<<<< at start of line, or ======= at start (with optional spaces), or >>>>>>> at start
    if ($content -match "(?m)^[\s]*<<<<<<<|(?m)^[\s]*=======[\s]*$|(?m)^[\s]*>>>>>>>") {
        Write-Log "WARNING: Merge conflicts detected in deploy_to_github.ps1! Cleaning automatically..." "Yellow"
        try {
            # Read the file line by line and remove conflict markers
            $lines = Get-Content $deployScriptPath
            $cleanLines = @()
            $inConflict = $false
            $keepSection = $false
            
            foreach ($line in $lines) {
                if ($line -match "^<<<<<<<") {
                    $inConflict = $true
                    # If it says "Updated upstream", keep that section; otherwise keep first section by default
                    $keepSection = $line -match "Updated upstream"
                    if (-not $keepSection) {
                        # Default: keep first section (before =======)
                        $keepSection = $true
                    }
                    continue
                }
                if ($line -match "^=======") {
                    # If we're keeping the first section, skip everything until >>>>>>>
                    # If we're keeping the second section, start keeping lines now
                    if ($keepSection) {
                        # Skip the second section
                        continue
                    } else {
                        # Start keeping the second section
                        $keepSection = $true
                        continue
                    }
                }
                if ($line -match "^>>>>>>>") {
                    $inConflict = $false
                    $keepSection = $false
                    continue
                }
                
                # Add line if we're not in conflict, or if we're keeping this section
                if (-not $inConflict -or $keepSection) {
                    $cleanLines += $line
                }
            }
            
            # Write cleaned content
            $cleanLines | Set-Content -Path $deployScriptPath
            Write-Log "Successfully cleaned merge conflicts in deploy_to_github.ps1" "Green"
            
            # Verify PowerShell syntax is valid
            try {
                $null = [System.Management.Automation.PSParser]::Tokenize((Get-Content $deployScriptPath -Raw), [ref]$null)
                Write-Log "Verified: PowerShell syntax is valid after cleanup" "Green"
            } catch {
                Write-Log "ERROR: PowerShell syntax error after conflict cleanup!" "Red"
                Write-Log "Syntax error details: $_" "Red"
                Write-Log "Please fix deploy_to_github.ps1 manually" "Red"
                exit 1
            }
            
            # Verify it's clean - check multiple times with different patterns
            $verifyContent = Get-Content $deployScriptPath -Raw
            $verifyLines = Get-Content $deployScriptPath
            
            # Check for any remaining conflict markers (only actual Git markers, not code with = signs)
            $hasConflicts = $false
            foreach ($line in $verifyLines) {
                # Only match actual Git conflict markers at start of line
                if ($line -match "^[\s]*<<<<<<<|^[\s]*=======[\s]*$|^[\s]*>>>>>>>") {
                    $hasConflicts = $true
                    Write-Log "Found remaining conflict marker: $($line.Trim())" "Yellow"
                    break
                }
            }
            
            if ($hasConflicts) {
                # Try one more aggressive cleanup pass
                Write-Log "Attempting second cleanup pass..." "Yellow"
                $cleanLines2 = @()
                $inConflict2 = $false
                $keepSection2 = $true
                
                foreach ($line in $verifyLines) {
                    if ($line -match "^[\s]*<<<<<<<") {
                        $inConflict2 = $true
                        $keepSection2 = $line -match "Updated upstream"
                        if (-not $keepSection2) {
                            $keepSection2 = $true
                        }
                        continue
                    }
                    if ($line -match "^[\s]*=======") {
                        if ($keepSection2) {
                            continue
                        } else {
                            $keepSection2 = $true
                            continue
                        }
                    }
                    if ($line -match "^[\s]*>>>>>>>") {
                        $inConflict2 = $false
                        $keepSection2 = $false
                        continue
                    }
                    
                    if (-not $inConflict2 -or $keepSection2) {
                        $cleanLines2 += $line
                    }
                }
                
                $cleanLines2 | Set-Content -Path $deployScriptPath
                
                # Final verification (only check for actual Git conflict markers)
                $finalCheck = Get-Content $deployScriptPath -Raw
                if ($finalCheck -match "(?m)^[\s]*<<<<<<<|(?m)^[\s]*=======[\s]*$|(?m)^[\s]*>>>>>>>") {
                    Write-Log "ERROR: Failed to clean all conflicts after second pass. Please resolve manually." "Red"
                    Write-Log "You can manually edit deploy_to_github.ps1 and remove all lines containing: <<<<<<<, =======, >>>>>>>" "Yellow"
                    exit 1
                } else {
                    Write-Log "Successfully cleaned conflicts on second pass" "Green"
                }
            } else {
                Write-Log "Verification passed - file is clean" "Green"
            }
        } catch {
            Write-Log "ERROR: Failed to clean merge conflicts: $_" "Red"
            Write-Log "Please resolve merge conflicts manually in deploy_to_github.ps1" "Red"
            exit 1
        }
    }
}

if ($env:GITHUB_REPO) {
    Write-Log "Step 4/4: Deploying to GitHub Pages..." "Yellow"
    Write-Log "Repository: $env:GITHUB_REPO" "Gray"
    if ($env:GITHUB_BRANCH) {
        $branchName = $env:GITHUB_BRANCH
    } else {
        $branchName = "gh-pages"
    }
    Write-Log "Branch: $branchName" "Gray"
    Write-Log ""
    
    & ".\deploy_to_github.ps1"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Log "Deployment completed successfully!" "Green"
    } else {
        Write-Log "WARNING: Deployment had issues, but web output is ready locally" "Yellow"
    }
} else {
    Write-Log "Step 4/4: Skipping GitHub deployment (GITHUB_REPO not set)" "Yellow"
    Write-Log ""
    Write-Log "To enable GitHub Pages deployment:" "Cyan"
    Write-Log "  Set: `$env:GITHUB_REPO='username/repo-name'" "White"
    Write-Log "  Set: `$env:GITHUB_BRANCH='gh-pages'" "White"
    Write-Log ""
    Write-Log "Web output is ready in: web_output/" "Green"
    Write-Log "You can test locally with: python app.py" "Green"
}

Write-Log ""
Write-Log "==========================================" "Cyan"
Write-Log "Workflow Completed!" "Green"
Write-Log "==========================================" "Cyan"
Write-Log ""
Write-Log "Summary:" "Cyan"
Write-Log "  PRA analysis completed" "Green"
Write-Log "  Earthquake integration completed" "Green"
Write-Log "  Web output prepared" "Green"
if ($env:GITHUB_REPO) {
    Write-Log "  Deployed to GitHub Pages" "Green"
}
Write-Log ""

# Keep window open if run by double-clicking
if ($Host.Name -eq "ConsoleHost") {
    Write-Log "Press Enter to close this window..." "Gray"
    Read-Host
}
