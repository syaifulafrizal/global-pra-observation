# Final fix: Change the anomaly detection logic
# The bug is on line ~236: if not is_anomalous and (not n_hours or n_hours == 0):
# This should be: if not is_anomalous or n_hours == 0:

import re

with open('upload_results.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the broken logic
old_logic = "if not is_anomalous and (not n_hours or n_hours == 0):"
new_logic = "if not is_anomalous or n_hours == 0:"

if old_logic in content:
    content = content.replace(old_logic, new_logic)
    with open('upload_results.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("[SUCCESS] Fixed anomaly detection logic!")
    print("Changed: if not is_anomalous and (not n_hours or n_hours == 0):")
    print("To:      if not is_anomalous or n_hours == 0:")
else:
    print("[ERROR] Could not find the line to fix")
