#!/usr/bin/env python3
"""
Final fix script for upload_results.py
Applies both critical fixes correctly
"""

# Read the file
with open('upload_results.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Track changes
changes_made = []

# Apply fixes
for i in range(len(lines)):
    line = lines[i]
    
    # Fix 1: Change the anomaly detection logic (around line 186)
    if "if not is_anomalous and (not n_hours or n_hours == 0):" in line:
        indent = len(line) - len(line.lstrip())
        lines[i] = " " * indent + "if not is_anomalous or n_hours == 0:\n"
        changes_made.append(f"Line {i+1}: Fixed anomaly logic (changed 'and' to 'or')")
    
    # Fix 2: Add date filtering (find the glob line)
    if "json_files = sorted(station_folder.glob('PRA_Night_*.json'))" in line:
        indent = len(line) - len(line.lstrip())
        new_lines = [
            " " * indent + "# CRITICAL FIX: Only process files for available dates\n",
            " " * indent + "if date_filter:\n",
            " " * (indent + 4) + "# Only check files for specific dates\n",
            " " * (indent + 4) + "json_files = []\n",
            " " * (indent + 4) + "for date in date_filter:\n",
            " " * (indent + 8) + "date_str = date.replace('-', '')\n",
            " " * (indent + 8) + "pattern = f'PRA_Night_{station}_{date_str}.json'\n",
            " " * (indent + 8) + "matching_files = list(station_folder.glob(pattern))\n",
            " " * (indent + 8) + "json_files.extend(matching_files)\n",
            " " * indent + "else:\n",
            " " * (indent + 4) + "# Fallback: process all files\n",
            " " * (indent + 4) + "json_files = sorted(station_folder.glob('PRA_Night_*.json'))\n"
        ]
        lines[i:i+1] = new_lines
        changes_made.append(f"Line {i+1}: Added date filtering")
        break  # Only do this once

# Write back
with open('upload_results.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

# Report
print("=" * 60)
print("FIXES APPLIED:")
print("=" * 60)
for change in changes_made:
    print(f"✓ {change}")

# Test syntax
print("\nTesting Python syntax...")
import subprocess
result = subprocess.run(['python', '-m', 'py_compile', 'upload_results.py'], 
                       capture_output=True, text=True)

if result.returncode == 0:
    print("✓ Syntax is VALID!")
    print("\nYou can now run: .\\deploy_all.bat")
else:
    print("✗ Syntax ERROR:")
    print(result.stderr)
    exit(1)
