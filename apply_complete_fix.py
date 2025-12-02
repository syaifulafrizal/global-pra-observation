# Complete fix for upload_results.py
# Applies both fixes in one go

with open('upload_results.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find and fix line 186: change the anomaly detection logic
for i, line in enumerate(lines):
    # Fix 1: Change the broken anomaly logic
    if "if not is_anomalous and (not n_hours or n_hours == 0):" in line:
        indent = len(line) - len(line.lstrip())
        lines[i] = " " * indent + "if not is_anomalous or n_hours == 0:\n"
        print(f"[FIX 1] Fixed anomaly logic at line {i+1}")
    
    # Fix 2: Add date filtering (find the glob line)
    if "json_files = sorted(station_folder.glob('PRA_Night_*.json'))" in line:
        indent = len(line) - len(line.lstrip())
        # Replace with date-filtered version
        new_code = [
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
        lines[i:i+1] = new_code
        print(f"[FIX 2] Added date filtering at line {i+1}")
        break

# Write back
with open('upload_results.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("\n[SUCCESS] Applied both fixes!")
print("Testing syntax...")

# Test syntax
import subprocess
result = subprocess.run(['python', '-m', 'py_compile', 'upload_results.py'], capture_output=True)
if result.returncode == 0:
    print("✓ Syntax is valid!")
else:
    print("✗ Syntax error:")
    print(result.stderr.decode())
