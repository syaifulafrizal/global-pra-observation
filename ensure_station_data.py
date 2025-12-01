#!/usr/bin/env python3
"""
Ensure latest INTERMAGNET data files exist before running the full workflow.

This script checks each station's local time. If the nighttime window (20:00-04:00)
has not yet completed, it ensures yesterday's data is downloaded. Once the window
has passed, it also verifies today's data so processing can proceed immediately.
"""

from datetime import datetime, timedelta
from pathlib import Path

from load_stations import load_stations
from pra_nighttime import (
    get_station_timezone,
    get_data_folder,
    download_data,
)


def ensure_station_files():
    stations = load_stations()
    if not stations:
        print('[WARNING] No stations found during preflight data check.')
        return 0

    total_downloads = 0

    for station in stations:
        code = station.get('code') if isinstance(station, dict) else station
        if not code:
            continue

        station_tz = get_station_timezone(code)
        now_local = datetime.now(station_tz)
        today_local = now_local.date()
        yesterday_local = today_local - timedelta(days=1)

        # Always ensure yesterday's data exists (used for fallback if today isn't ready)
        dates_to_check = {yesterday_local}

        if now_local.hour >= 4:
            # After 04:00 local time, the nighttime window has completed.
            dates_to_check.add(today_local)
        else:
            # Before 04:00, ensure two days ago is available to prevent stale displays.
            dates_to_check.add(today_local - timedelta(days=2))

        data_folder = get_data_folder(code)
        data_folder.mkdir(parents=True, exist_ok=True)

        for date_obj in dates_to_check:
            if not date_obj:
                continue
            # Do not request future dates
            if date_obj > today_local:
                continue

            target_dt = datetime.combine(date_obj, datetime.min.time()).replace(tzinfo=station_tz)
            filename = f'{code}_{date_obj.strftime("%Y%m%d")}.iaga2002'
            data_path = data_folder / filename
            if data_path.exists() and data_path.stat().st_size > 0:
                continue

            result = download_data(code, target_dt, data_folder)
            if result and result.exists():
                total_downloads += 1
                print(f'[OK] Downloaded {code} data for {date_obj}')
            else:
                print(f'[WARN] Could not download {code} data for {date_obj}')

    print(f'[INFO] Preflight data check complete. New files downloaded: {total_downloads}')
    return 0


if __name__ == '__main__':
    exit(ensure_station_files())

