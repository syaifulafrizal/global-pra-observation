# Quick fix script for upload_results.py
# This adds the date filter to only process recent PRA files

import re

# Read the file
with open('upload_results.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the problematic line
old_code = "        json_files = sorted(station_folder.glob('PRA_Night_*.json'))"

new_code = """        # CRITICAL FIX: Only process files for available dates
        if date_filter:
            # Only check files for specific dates
            json_files = []
            for date in date_filter:
                date_str = date.replace('-', '')
                pattern = f'PRA_Night_{station}_{date_str}.json'
                matching_files = list(station_folder.glob(pattern))
                json_files.extend(matching_files)
        else:
            # Fallback: process all files
            json_files = sorted(station_folder.glob('PRA_Night_*.json'))"""

if old_code in content:
    content = content.replace(old_code, new_code)
    
    # Write back
    with open('upload_results.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("[SUCCESS] Fixed upload_results.py!")
    print("Now run: .\\deploy_all.bat")
else:
    print("[ERROR] Could not find the line to replace")
    print("The file may have already been modified")
