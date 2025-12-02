# Add detailed logging to upload_results.py
# This will show exactly where each anomaly comes from

import re

# Read the file
with open('upload_results.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add logging after the date filter section
old_section = """    for station in stations:
        station_folder = Path('INTERMAGNET_DOWNLOADS') / station
        if not station_folder.exists():
            continue
        # CRITICAL FIX: Only process files for available dates
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
            json_files = sorted(station_folder.glob('PRA_Night_*.json'))
        for json_file in json_files:"""

new_section = """    print(f'[DEBUG] Processing {len(stations)} stations for dates: {date_filter}')
    anomalies_added = 0
    
    for station in stations:
        station_folder = Path('INTERMAGNET_DOWNLOADS') / station
        if not station_folder.exists():
            continue
        # CRITICAL FIX: Only process files for available dates
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
            json_files = sorted(station_folder.glob('PRA_Night_*.json'))
        
        if json_files:
            print(f'[DEBUG] Station {station}: Found {len(json_files)} files to process')
        
        for json_file in json_files:"""

# Replace
if old_section in content:
    content = content.replace(old_section, new_section)
    print("[STEP 1] Added station-level logging")
else:
    print("[WARNING] Could not find station loop section")

# Add logging when anomaly is added
old_add = """            entry_map[key] = entry
            updated = True"""

new_add = """            entry_map[key] = entry
            updated = True
            anomalies_added += 1
            print(f'[ANOMALY] Added: {station} on {event_date} (n_hours={n_hours}, has_eq={entry[\"has_correlated_eq\"]})')"""

if old_add in content:
    content = content.replace(old_add, new_add)
    print("[STEP 2] Added anomaly logging")
else:
    print("[WARNING] Could not find anomaly add section")

# Add summary logging
old_summary = """    if retroactive_updates > 0:
        print(f'[INFO] Updated {retroactive_updates} anomalies with retroactive EQ correlations')
    
    if updated:"""

new_summary = """    if retroactive_updates > 0:
        print(f'[INFO] Updated {retroactive_updates} anomalies with retroactive EQ correlations')
    
    print(f'[DEBUG] Total anomalies added this run: {anomalies_added}')
    print(f'[DEBUG] Total entries in history: {len(entry_map)}')
    
    if updated:"""

if old_summary in content:
    content = content.replace(old_summary, new_summary)
    print("[STEP 3] Added summary logging")
else:
    print("[WARNING] Could not find summary section")

# Write back
with open('upload_results.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("\n[SUCCESS] Added detailed logging to upload_results.py!")
print("Now run: .\\deploy_all.bat")
print("You will see exactly which files are processed and which anomalies are added!")
