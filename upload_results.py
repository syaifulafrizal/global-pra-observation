#!/usr/bin/env python3
"""
Prepare processed results for local web serving
Prepares files in web_output/ directory for Flask to serve
Handles date-specific files and 7-day data retention
"""

import os
import json
import re
import csv
from pathlib import Path
from datetime import datetime, timedelta
import shutil
import math
from result_validation import result_is_usable

# Configuration
OUTPUT_DIR = Path('web_output')  # Directory for prepared web files
ANOMALY_HISTORY_FILENAME = 'anomaly_history.json'
FALSE_NEGATIVE_HISTORY_FILENAME = 'false_negative_history.json'
HISTORY_SKIP_FILES = {
    'stations.json',
    ANOMALY_HISTORY_FILENAME,
    FALSE_NEGATIVE_HISTORY_FILENAME
}
RUN_ID = os.getenv('PRA_RUN_ID', 'manual')
HISTORY_DIR = Path('data') / 'history'
ANOMALY_HISTORY_PATH = HISTORY_DIR / ANOMALY_HISTORY_FILENAME
FALSE_NEGATIVE_HISTORY_PATH = HISTORY_DIR / FALSE_NEGATIVE_HISTORY_FILENAME
RUN_REPORT_DIR = Path('data') / 'run_reports'
RUN_REPORT_SNAPSHOT = 'run_report_latest.json'

def parse_date_from_filename(filename):
    """Extract date from filename in format YYYY-MM-DD"""
    # Try to match date patterns like 2025-11-18 or 20251118
    date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
    if date_match:
        return date_match.group(0)
    date_match = re.search(r'(\d{4})(\d{2})(\d{2})', filename)
    if date_match:
        return f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
    return None

def get_available_dates(stations=None):
    """Advertise the latest seven actual usable station-night dates, never guesses."""
    dates = set()
    for station in stations if stations is not None else get_stations():
        for path in (Path('INTERMAGNET_DOWNLOADS') / station).glob('PRA_Night_*.json'):
            day = parse_date_from_filename(path.name)
            try:
                datetime.strptime(day, '%Y-%m-%d')
                result = json.loads(path.read_text(encoding='utf-8'))
                if result.get('date') == day and result_is_usable(result):
                    dates.add(day)
            except (ValueError, TypeError, OSError):
                continue
    return sorted(dates, reverse=True)[:7]

def cleanup_old_files(data_dir, figures_dir, cutoff_date, skip_files=None):
    """Remove files older than cutoff_date"""
    deleted_count = 0
    skip_files = skip_files or set()
    
    # Clean JSON files in data/
    if data_dir.exists():
        for json_file in data_dir.glob('*.json'):
            if json_file.name in skip_files:
                continue
            if json_file.name != 'stations.json':
                file_date = parse_date_from_filename(json_file.name)
                if file_date:
                    try:
                        file_date_obj = datetime.strptime(file_date, '%Y-%m-%d').date()
                        if file_date_obj < cutoff_date:
                            json_file.unlink()
                            deleted_count += 1
                    except ValueError:
                        pass
    
    # Clean PNG files in figures/
    if figures_dir.exists():
        for png_file in figures_dir.rglob('*.png'):
            file_date = parse_date_from_filename(png_file.name)
            if file_date:
                try:
                    file_date_obj = datetime.strptime(file_date, '%Y-%m-%d').date()
                    if file_date_obj < cutoff_date:
                        png_file.unlink()
                        deleted_count += 1
                except ValueError:
                    pass
    
    return deleted_count

def load_history_entries(file_path):
    """Load history entries from a JSON file"""
    if file_path.exists():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get('entries'), list):
                    return data['entries']
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []

def save_history_entries(file_path, entries):
    """Persist history entries back to disk"""
    payload = {
        'last_updated': datetime.utcnow().isoformat(),
        'entries': entries
    }
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)

def safe_float(value):
    """Convert value to float if possible"""
    try:
        if value is None or value == '':
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None

def parse_any_date(value):
    """Parse a string into a date object (YYYY-MM-DD)"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        pass
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(str(value).split(' ')[0], fmt).date()
        except ValueError:
            continue
    return None


def normalize_date_string(value):
    """Convert various date strings to YYYY-MM-DD."""
    date = parse_any_date(value)
    if date:
        return date.strftime('%Y-%m-%d')
    return None


def build_run_report(stations, available_dates, anomaly_history, false_negative_history, data_dir):
    """Build and persist run report summarizing recent performance."""
    timestamp = datetime.utcnow().isoformat()
    latest_date = available_dates[0] if available_dates else None
    window_dates = set(available_dates or [])

    def in_window(value):
        if not window_dates:
            return False
        normalized = normalize_date_string(value)
        return normalized in window_dates

    anomalies_last_day = 0
    anomalies_last_week = 0
    correlated_last_week = 0
    for entry in anomaly_history:
        entry_date = normalize_date_string(entry.get('date'))
        if entry_date == latest_date:
            anomalies_last_day += 1
        if entry_date and entry_date in window_dates:
            anomalies_last_week += 1
            if entry.get('has_correlated_eq'):
                correlated_last_week += 1

    false_negatives_last_week = sum(
        1 for entry in false_negative_history
        if in_window(entry.get('earthquake_time') or entry.get('date'))
    )

    total_correlated = sum(1 for entry in anomaly_history if entry.get('has_correlated_eq'))
    total_false_positives = sum(entry.get('status') == 'FP' for entry in anomaly_history)

    recent_anomalies = [
        entry for entry in anomaly_history
        if in_window(entry.get('date'))
    ]
    recent_anomalies.sort(key=lambda e: e.get('date', ''), reverse=True)

    recent_false_negatives = [
        entry for entry in false_negative_history
        if in_window(entry.get('earthquake_time') or entry.get('date'))
    ]
    recent_false_negatives.sort(
        key=lambda e: (e.get('earthquake_time') or e.get('date') or ''),
        reverse=True
    )

    report = {
        'run_id': RUN_ID,
        'generated_at': timestamp,
        'latest_date': latest_date,
        'available_dates': available_dates,
        'stations_processed': len(stations),
        'metrics': {
            'anomalies_last_day': anomalies_last_day,
            'anomalies_last_7_days': anomalies_last_week,
            'correlated_last_7_days': correlated_last_week,
            'false_positives_last_7_days': sum(in_window(e.get('date')) and e.get('status') == 'FP' for e in anomaly_history),
            'pending_anomalies': sum(e.get('status') == 'Pending' for e in anomaly_history),
            'unverified_anomalies': sum(e.get('status') == 'Unknown' for e in anomaly_history),
            'false_negatives_last_7_days': false_negatives_last_week,
            'total_anomalies': len(anomaly_history),
            'total_correlated': total_correlated,
            'total_false_positives': total_false_positives,
            'total_false_negatives': len(false_negative_history),
        },
        'recent_anomalies': recent_anomalies[:50],
        'recent_false_negatives': recent_false_negatives[:50],
    }

    RUN_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RUN_REPORT_DIR / f'run_report_{RUN_ID}.json'
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    snapshot_path = RUN_REPORT_DIR / RUN_REPORT_SNAPSHOT
    with open(snapshot_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    # Copy snapshot into prepared data directory for frontend use
    shutil.copy(snapshot_path, data_dir / RUN_REPORT_SNAPSHOT)
    return report

def correlation_date(row):
    """Canonical result date is the end of the local nighttime range."""
    value = row.get('anomaly_range')
    if value and ' - ' in str(value):
        return normalize_date_string(str(value).split(' - ')[1].split()[0])
    return normalize_date_string(row.get('anomaly_date') or row.get('anomalyDate'))


def correlation_row_status(row):
    """Legacy backward-looking matches cannot validate a forward forecast."""
    status = row.get('status')
    detection = row.get('detection_time_utc')
    magnitude = safe_float(row.get('earthquake_magnitude') or row.get('magnitude'))
    if status == 'TP' or (not status and magnitude is not None):
        if not detection or magnitude is None or magnitude < 5:
            return 'Unknown'
        try:
            from earthquake_integration import utc_naive
            elapsed = utc_naive(row['earthquake_time']) - utc_naive(detection)
            return 'TP' if timedelta(0) <= elapsed <= timedelta(days=14) else 'Unknown'
        except (ValueError, KeyError, TypeError):
            return 'Unknown'
    if status == 'FP':
        try:
            from earthquake_integration import utc_naive
            elapsed = datetime.utcnow() - utc_naive(detection)
            return 'FP' if magnitude is None and elapsed >= timedelta(days=14) else 'Unknown'
        except (ValueError, TypeError):
            return 'Unknown'
    return status if status in ('Pending', 'Unknown') else 'Unknown'


def read_correlations(station_folder, target_date):
    path = station_folder / 'earthquake_correlations.csv'
    if not path.exists():
        return []
    try:
        with path.open(encoding='utf-8') as source:
            rows = [dict(row) for row in csv.DictReader(source) if correlation_date(row) == target_date]
        for row in rows:
            row['status'] = correlation_row_status(row)
        return rows
    except (OSError, ValueError):
        return []


def station_correlation_status(station_folder, target_date):
    statuses = [row['status'] for row in read_correlations(station_folder, target_date)]
    for status in ('TP', 'FP', 'Pending', 'Unknown'):
        if status in statuses:
            return status
    return 'Unknown'


def station_has_correlation(station_folder, target_date):
    return station_correlation_status(station_folder, target_date) == 'TP'


def merge_history(path, archive, keys):
    entries = {}
    for entry in load_history_entries(archive) + load_history_entries(path):
        key = tuple(entry.get(name) for name in keys)
        if all(key):
            previous = entries.get(key, {})
            if str(entry.get('last_confirmed', '')) >= str(previous.get('last_confirmed', '')):
                entries[key] = entry
    return list(entries.values())


def update_anomaly_history(stations, data_dir, available_dates=None):
    """Append new anomalies to the persistent history log and retroactively link earthquakes
    
    This function:
    1. Keeps ALL anomalies ever detected (persistent history)
    2. Processes new anomalies from recent dates
    3. Refreshes verified forward correlations within 14 days after detection
    
    Args:
        stations: List of station codes
        data_dir: Directory containing history files
        available_dates: List of recent dates to check for NEW anomalies
    """
    history_path = data_dir / ANOMALY_HISTORY_FILENAME
    entries = merge_history(history_path, ANOMALY_HISTORY_PATH, ('station', 'date'))
    entry_map = {}
    for entry in entries:
        station = entry.get('station')
        date = entry.get('date')
        if station and date:
            entry_map[f'{station}|{date}'] = entry
    updated = False
    now_iso = datetime.utcnow().isoformat()
    
    # Convert available_dates to set for faster lookup (only for NEW anomalies)
    date_filter = set(available_dates) if available_dates else None
    
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
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    station_data = json.load(f)
            except Exception:
                continue
            
            # Get the date first
            event_date = station_data.get('date') or parse_date_from_filename(json_file.name)
            if not event_date:
                continue
            
            # Only process NEW anomalies from recent dates
            # But keep all existing anomalies in history
            is_new_anomaly = date_filter and event_date in date_filter
            key = f'{station}|{event_date}'
            already_exists = key in entry_map
            
            # Skip if not a new anomaly and already exists
            if not is_new_anomaly and already_exists:
                continue
            
            is_anomalous = result_is_usable(station_data) and bool(station_data.get('is_anomalous'))
            n_hours = station_data.get('nAnomHours') or station_data.get('n_anom_hours') or 0
            
            # CRITICAL FIX: Skip if NOT anomalous OR if n_hours is 0
            # Must be anomalous AND have hours > 0 to be added
            if not is_anomalous or n_hours == 0:
                continue
            
            # Only process if it's a new anomaly from recent dates
            if not is_new_anomaly:
                continue
            
            entry = entry_map.get(key, {
                'station': station,
                'date': event_date,
                'first_detected': now_iso
            })
            entry['threshold'] = station_data.get('threshold')
            entry['n_anomaly_hours'] = n_hours
            entry['source_file'] = json_file.name
            entry['last_confirmed'] = now_iso
            
            # Keep match, pending, false-positive and unknown states distinct.
            entry['status'] = station_correlation_status(station_folder, event_date)
            entry['has_correlated_eq'] = entry['status'] == 'TP'
            
            entry_map[key] = entry
            updated = True
    
    # RETROACTIVE LINKING: Check all existing anomalies for new earthquakes
    # This handles events within 14 days after detection.
    print('[INFO] Checking for retroactive earthquake correlations...')
    retroactive_updates = 0
    for key, entry in entry_map.items():
        station = entry.get('station')
        event_date = entry.get('date')
        if not station or not event_date:
            continue
        
        station_folder = Path('INTERMAGNET_DOWNLOADS') / station
        if not station_folder.exists():
            continue
        
        # Re-check earthquake correlation (may have changed if new EQ occurred)
        old_status = entry.get('has_correlated_eq', False)
        classification = station_correlation_status(station_folder, event_date)
        new_status = classification == 'TP'
        
        if old_status != new_status or entry.get('status') != classification:
            entry['status'] = classification
            entry['has_correlated_eq'] = new_status
            entry['last_confirmed'] = now_iso
            updated = True
            retroactive_updates += 1
    
    if retroactive_updates > 0:
        print(f'[INFO] Updated {retroactive_updates} anomalies with retroactive EQ correlations')
    
    if updated or entries:
        sorted_entries = sorted(
            entry_map.values(),
            key=lambda e: (e.get('date', ''), e.get('station', ''))
        )
        save_history_entries(history_path, sorted_entries)
        
        # Count true positives and false positives
        true_positives = sum(1 for e in sorted_entries if e.get('has_correlated_eq'))
        false_positives = sum(e.get('status') == 'FP' for e in sorted_entries)
        
        print(f'[INFO] Updated anomaly history: {len(sorted_entries)} total anomalies')
        print(f'[INFO]   True Positives: {true_positives} (with correlated EQ)')
        print(f'[INFO]   False Positives: {false_positives} (no correlated EQ)')
    else:
        # Ensure file exists even if no update occurred
        if not history_path.exists():
            sorted_entries = sorted(entries, key=lambda e: (e.get('date', ''), e.get('station', '')))
            save_history_entries(history_path, sorted_entries)
    entries = load_history_entries(history_path)
    # Persist to history directory for long-term aggregation
    if entries:
        save_history_entries(ANOMALY_HISTORY_PATH, entries)
    return entries

def update_false_negative_history(stations, data_dir):
    """Ensure false negative history stays cumulative"""
    history_path = data_dir / FALSE_NEGATIVE_HISTORY_FILENAME
    entries = merge_history(history_path, FALSE_NEGATIVE_HISTORY_PATH, ('station', 'earthquake_time'))
    entry_map = {}
    for entry in entries:
        station = entry.get('station')
        eq_time = entry.get('earthquake_time')
        if station and eq_time:
            entry_map[f'{station}|{eq_time}'] = entry
    updated = False
    now_iso = datetime.utcnow().isoformat()
    for station in stations:
        station_folder = Path('INTERMAGNET_DOWNLOADS') / station
        csv_path = station_folder / 'false_negatives.csv'
        if not csv_path.exists():
            continue
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    eq_time = row.get('earthquake_time') or row.get('time')
                    if not eq_time:
                        continue
                    key = f'{station}|{eq_time}'
                    entry = entry_map.get(key, {
                        'station': station,
                        'earthquake_time': eq_time,
                        'first_logged': now_iso
                    })
                    entry['earthquake_magnitude'] = safe_float(row.get('earthquake_magnitude') or row.get('magnitude'))
                    entry['earthquake_distance_km'] = safe_float(row.get('earthquake_distance_km') or row.get('distance_km'))
                    entry['earthquake_place'] = row.get('earthquake_place') or row.get('place')
                    entry['earthquake_latitude'] = safe_float(row.get('earthquake_latitude') or row.get('latitude'))
                    entry['earthquake_longitude'] = safe_float(row.get('earthquake_longitude') or row.get('longitude'))
                    entry['last_confirmed'] = now_iso
                    entry['source_file'] = csv_path.name
                    entry['coverage_verified'] = str(row.get('coverage_verified', '')).lower() == 'true'
                    entry_map[key] = entry
                    updated = True
        except Exception:
            continue
    if updated or entries:
        sorted_entries = sorted(
            entry_map.values(),
            key=lambda e: (e.get('earthquake_time', ''), e.get('station', ''))
        )
        save_history_entries(history_path, sorted_entries)
        print(f'[INFO] Updated false negative history with {len(sorted_entries)} total entries')
    else:
        if not history_path.exists():
            save_history_entries(history_path, entries)
    entries = load_history_entries(history_path)
    if entries:
        save_history_entries(FALSE_NEGATIVE_HISTORY_PATH, entries)
    return entries

def get_stations():
    """Get list of stations - auto-detect from processed data or use env var"""
    stations_env = os.getenv('INTERMAGNET_STATIONS', '')
    if stations_env:
        return [s.strip() for s in stations_env.split(',')]
    
    # Auto-detect: Find all stations that have been processed
    downloads_dir = Path('INTERMAGNET_DOWNLOADS')
    if downloads_dir.exists():
        stations = []
        for station_dir in downloads_dir.iterdir():
            if station_dir.is_dir() and not station_dir.name.startswith('.'):
                # Check if this station has processed JSON files
                json_files = list(station_dir.glob('PRA_Night_*.json'))
                if json_files:
                    stations.append(station_dir.name)
        
        if stations:
            stations.sort()
            print(f'[INFO] Auto-detected {len(stations)} processed stations')
            return stations
    
    # Fallback: Try to load from stations.json
    if Path('stations.json').exists():
        try:
            with open('stations.json', 'r') as f:
                data = json.load(f)
                if isinstance(data, dict) and 'stations' in data:
                    if isinstance(data['stations'], list):
                        return [row['code'] if isinstance(row, dict) else row for row in data['stations']]
                    elif isinstance(data['stations'], dict):
                        return list(data['stations'].keys())
        except Exception:
            pass
    
    # Last resort: raise error
    raise ValueError("No stations found. Please ensure data has been processed.")

def load_station_metadata():
    try:
        data = json.loads(Path('stations.json').read_text(encoding='utf-8'))
        return {row['code']: {key: value for key, value in row.items() if key != 'code'}
                for row in data.get('stations', []) if isinstance(row, dict) and 'code' in row}
    except (ValueError, OSError):
        return {}


def build_aggregated_data(stations, date, data_dir, source_folder=None):
    """Build one snapshot without writing, for preparation and local Flask use."""
    snapshot = {'date': date, 'generated_at': datetime.utcnow().isoformat(),
                'stations': {}, 'earthquake_correlations': {}, 'false_negatives': {},
                'metadata': load_station_metadata(), 'station_dates': {}, 'station_quality': {}}
    for station in stations:
        station_folder = Path(source_folder or 'INTERMAGNET_DOWNLOADS') / station
        actual_date = date
        def result_path(day):
            if source_folder is not None:
                return station_folder / f'PRA_Night_{station}_{day.replace("-", "")}.json'
            return data_dir / f'{station}_{day}.json'
        path = result_path(date)
        if not path.exists():
            actual_date = (datetime.strptime(date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
            path = result_path(actual_date)
        if not path.exists():
            snapshot['station_quality'][station] = 'missing'
            continue
        try:
            result = json.loads(path.read_text(encoding='utf-8'))
            if result.get('date') != actual_date or not result_is_usable(result):
                snapshot['station_quality'][station] = 'invalid'
                continue
            snapshot['stations'][station] = result
            snapshot['station_dates'][station] = actual_date
            snapshot['station_quality'][station] = result.get('data_quality', {}).get('status', 'unverified')
        except (ValueError, OSError, TypeError):
            snapshot['station_quality'][station] = 'invalid'
            continue
        correlations = read_correlations(station_folder, actual_date)
        if correlations:
            snapshot['earthquake_correlations'][station] = correlations
        path = station_folder / 'false_negatives.csv'
        if path.exists():
            try:
                with path.open(encoding='utf-8') as source:
                    rows = [dict(row) for row in csv.DictReader(source)
                            if normalize_date_string(row.get('earthquake_time')) == date]
                if rows:
                    snapshot['false_negatives'][station] = rows
            except (ValueError, OSError):
                pass
    snapshot['is_hybrid_aggregation'] = any(day != date for day in snapshot['station_dates'].values())
    return snapshot


def generate_aggregated_data_files(stations, available_dates, data_dir):
    count = 0
    for date in available_dates:
        snapshot = build_aggregated_data(stations, date, data_dir,
                                         source_folder=Path('INTERMAGNET_DOWNLOADS'))
        if snapshot['stations']:
            with (data_dir / f'aggregated_{date}.json').open('w', encoding='utf-8') as destination:
                json.dump(snapshot, destination, indent=2)
            count += 1
    return count


def prepare_web_output():
    """Prepare static files for web deployment with date-specific handling"""
    print('Preparing web output...')
    stations = get_stations()
    available_dates = get_available_dates(stations)
    if not available_dates:
        raise ValueError('No usable station-night results; preserving the existing published output')
    
    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Copy static frontend files
    static_dir = OUTPUT_DIR / 'static'
    static_dir.mkdir(exist_ok=True)
    
    # Copy CSS
    if Path('static/style.css').exists():
        shutil.copy('static/style.css', static_dir / 'style.css')
    
    # Copy JS
    if Path('static/app.js').exists():
        shutil.copy('static/app.js', static_dir / 'app.js')

    # Keep generated branding assets in the same portable static bundle.
    assets_dir = Path('static/assets')
    if assets_dir.exists():
        shutil.copytree(assets_dir, static_dir / 'assets', dirs_exist_ok=True)
    
    # Create data and figures directories
    data_dir = OUTPUT_DIR / 'data'
    data_dir.mkdir(exist_ok=True)
    
    figures_dir = OUTPUT_DIR / 'figures'
    figures_dir.mkdir(exist_ok=True)
    
    # Use dates backed by actual usable results, including during upstream delays.
    most_recent_date = available_dates[0] if available_dates else None
    
    print(f'[INFO] Available dates: {", ".join(available_dates)}')
    print(f'[INFO] Most recent date: {most_recent_date}')
    
    # Copy date-specific files for the last 7 days
    cutoff_date = datetime.strptime(available_dates[-1], '%Y-%m-%d').date()
    
    for station in stations:
        station_folder = Path('INTERMAGNET_DOWNLOADS') / station
        
        if not station_folder.exists():
            continue
        
        # Copy date-specific JSON files
        # Note: JSON files are named with "today's" date but contain data from yesterday 20:00 to today 04:00
        # Keep this canonical end-of-night date; never alias another night.
        json_files = list(station_folder.glob('PRA_Night_*.json'))
        for json_file in json_files:
            file_date = parse_date_from_filename(json_file.name)
            if file_date:
                try:
                    file_date_obj = datetime.strptime(file_date, '%Y-%m-%d').date()
                    if file_date_obj >= cutoff_date:
                        # Copy as {station}_{date}.json (always copy if within date range, not just if in available_dates)
                        # This ensures files are available even if they're not in the standard 7-day window
                        dest_file = data_dir / f'{station}_{file_date}.json'
                        shutil.copy(json_file, dest_file)
                        print(f'[INFO] Copied {station}_{file_date}.json')
                        
                except ValueError:
                    pass
        
        # Copy date-specific figures
        station_figures_dir = station_folder / 'figures'
        if station_figures_dir.exists():
            web_station_figures_dir = figures_dir / station
            web_station_figures_dir.mkdir(exist_ok=True)
            
            for fig_file in station_figures_dir.glob('*.png'):
                file_date = parse_date_from_filename(fig_file.name)
                if file_date and file_date in available_dates:
                    try:
                        file_date_obj = datetime.strptime(file_date, '%Y-%m-%d').date()
                        if file_date_obj >= cutoff_date:
                            shutil.copy(fig_file, web_station_figures_dir / fig_file.name)
                    except ValueError:
                        pass

        # Copy supporting CSVs (earthquake correlations, false negatives)
        eq_corr_path = station_folder / 'earthquake_correlations.csv'
        if eq_corr_path.exists():
            shutil.copy(eq_corr_path, data_dir / f'{station}_earthquake_correlations.csv')
        fn_path = station_folder / 'false_negatives.csv'
        if fn_path.exists():
            shutil.copy(fn_path, data_dir / f'{station}_false_negatives.csv')
    
    # Copy date-specific earthquake files
    for date in available_dates:
        eq_csv = Path(f'recent_earthquakes_{date}.csv')
        if eq_csv.exists():
            shutil.copy(eq_csv, data_dir / eq_csv.name)
        elif not (data_dir / eq_csv.name).exists():
            (data_dir / eq_csv.name).write_text('time,latitude,longitude,depth,magnitude,place\n', encoding='utf-8')

            
        # Copy date-specific earthquake stats (for summary boxes)
        eq_stats = Path(f'earthquake_stats_{date}.json')
        if eq_stats.exists():
            shutil.copy(eq_stats, data_dir / eq_stats.name)
        elif not (data_dir / eq_stats.name).exists():
            # Missing context is explicitly unknown, never a measured zero.
            (data_dir / eq_stats.name).write_text(json.dumps({
                'analysis_date': date, 'global_count': None, 'within_200km_count': None,
                'data_status': 'unavailable',
            }, indent=2), encoding='utf-8')

    
    # Clean up old files (older than 6 days)
    deleted = cleanup_old_files(data_dir, figures_dir, cutoff_date, skip_files=HISTORY_SKIP_FILES)
    if deleted > 0:
        print(f'[INFO] Cleaned up {deleted} old files')

    # Keep cumulative anomaly and false negative histories
    anomaly_history = update_anomaly_history(stations, data_dir, available_dates)
    false_negative_history = update_false_negative_history(stations, data_dir)
    run_report = build_run_report(stations, available_dates, anomaly_history, false_negative_history, data_dir)
    
    # Generate aggregated data files for faster frontend loading
    # This combines all station data per date into single JSON files
    generate_aggregated_data_files(stations, available_dates, data_dir)
    
    # Load station metadata from root stations.json
    metadata_dict = {}
    if Path('stations.json').exists():
        try:
            with open('stations.json', 'r', encoding='utf-8') as f:
                stations_metadata = json.load(f)
                
            # Handle different formats of stations.json
            if isinstance(stations_metadata, dict):
                if 'stations' in stations_metadata:
                    # Format 1: {"stations": [{"code": "KAK", "name": "...", ...}, ...]}
                    if isinstance(stations_metadata['stations'], list):
                        for station_obj in stations_metadata['stations']:
                            if isinstance(station_obj, dict) and 'code' in station_obj:
                                code = station_obj['code']
                                metadata_dict[code] = {
                                    'name': station_obj.get('name', ''),
                                    'country': station_obj.get('country', ''),
                                    'latitude': station_obj.get('latitude', 0),
                                    'longitude': station_obj.get('longitude', 0),
                                    'timezone': station_obj.get('timezone', '')
                                }
                        if metadata_dict:
                            print(f'[INFO] Loaded metadata for {len(metadata_dict)} stations from root stations.json')
                    # Format 2: {"stations": {"KAK": {...}, ...}}
                    elif isinstance(stations_metadata['stations'], dict):
                        metadata_dict = stations_metadata['stations']
                        print(f'[INFO] Loaded metadata for {len(metadata_dict)} stations from root stations.json (dict format)')
                # Format 3: {"metadata": [...]} - array of metadata objects
                elif 'metadata' in stations_metadata and isinstance(stations_metadata['metadata'], list):
                    for station_obj in stations_metadata['metadata']:
                        if isinstance(station_obj, dict) and 'code' in station_obj:
                            code = station_obj['code']
                            metadata_dict[code] = {
                                'name': station_obj.get('name', ''),
                                'country': station_obj.get('country', ''),
                                'latitude': station_obj.get('latitude', 0),
                                'longitude': station_obj.get('longitude', 0),
                                'timezone': station_obj.get('timezone', '')
                            }
                    if metadata_dict:
                        print(f'[INFO] Loaded metadata for {len(metadata_dict)} stations from metadata array')
        except Exception as e:
            print(f'[WARNING] Could not load station metadata: {e}')
            import traceback
            traceback.print_exc()
    
    # Create stations.json with available dates and metadata
    stations_json = {
        'stations': stations,
        'available_dates': available_dates,
        'most_recent_date': most_recent_date,
        'last_updated': datetime.now().isoformat(),
    }
    
    # Add station metadata - ensure all stations have at least empty metadata
    if metadata_dict:
        print(f'[INFO] Using metadata for {len(metadata_dict)} stations')
        # Only include metadata for stations that are actually processed
        filtered_metadata = {code: metadata_dict[code] for code in stations if code in metadata_dict}
        stations_json['metadata'] = filtered_metadata
        # Add empty metadata for stations without metadata
        for station in stations:
            if station not in stations_json['metadata']:
                stations_json['metadata'][station] = {}
        print(f'[INFO] Final metadata contains {len(stations_json["metadata"])} stations')
    else:
        print(f'[WARNING] No metadata found, creating empty metadata for {len(stations)} stations')
        # If no metadata found, create empty dict for all stations
        stations_json['metadata'] = {s: {} for s in stations}
    
    with open(data_dir / 'stations.json', 'w') as f:
        json.dump(stations_json, f, indent=2)
    
    # Copy index.html directly from template
    template_path = Path('templates/index.html')
    if template_path.exists():
        shutil.copy(template_path, OUTPUT_DIR / 'index.html')
        print('[OK] Copied index.html from template')
    else:
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    print(f'[OK] Web output prepared in {OUTPUT_DIR}')
    return OUTPUT_DIR, anomaly_history, false_negative_history, run_report

def main():
    """Main function - prepare files for local serving"""
    print('='*60)
    print('PRA Results Preparation Script')
    print('='*60)
    
    # Prepare web output
    output_dir, anomaly_history, false_negative_history, run_report = prepare_web_output()

    
    print('\n[OK] Files prepared successfully!')
    print(f'\nOutput directory: {output_dir.absolute()}')
    print('\nTo view the dashboard:')
    print('   python app.py')
    print('   Then open: http://localhost:5000')
    print('\nThe Flask app will serve files directly from:')
    print('   - web_output/ (prepared files)')
    print('   - INTERMAGNET_DOWNLOADS/ (source data)')
    
    return 0

if __name__ == '__main__':
    exit(main())
