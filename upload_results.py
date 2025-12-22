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
HISTORY_DIR.mkdir(parents=True, exist_ok=True)
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

def get_available_dates():
    """Get list of available dates (last 7 days)"""
    dates = []
    today = datetime.now().date()
    for i in range(7):
        date = today - timedelta(days=i)
        dates.append(date.strftime('%Y-%m-%d'))
    return dates

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
        return float(value)
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
    total_false_positives = len(anomaly_history) - total_correlated

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
            'false_positives_last_7_days': anomalies_last_week - correlated_last_week,
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

def station_has_correlation(station_folder, target_date):
    """Check if a station has an earthquake correlation for a specific date"""
    if not target_date:
        return False
    csv_path = station_folder / 'earthquake_correlations.csv'
    if not csv_path.exists():
        return False
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                date_value = (
                    row.get('anomaly_date') or
                    row.get('anomaly_date ') or
                    row.get('anomaly_date'.upper()) or
                    row.get('anomalyDate')
                )
                anomaly_date = parse_any_date(date_value)
                if not anomaly_date:
                    continue
                if anomaly_date.strftime('%Y-%m-%d') != target_date:
                    continue
                magnitude = safe_float(row.get('earthquake_magnitude') or row.get('magnitude'))
                if magnitude is None:
                    magnitude = safe_float(row.get('earthquakeMag'))
                if magnitude is None or magnitude >= 5.0:
                    return True
    except Exception:
        return False
    return False

def update_anomaly_history(stations, data_dir, available_dates=None):
    """Append new anomalies to the persistent history log and retroactively link earthquakes
    
    This function:
    1. Keeps ALL anomalies ever detected (persistent history)
    2. Processes new anomalies from recent dates
    3. Retroactively links earthquakes that occurred 14-30 days AFTER anomalies
    
    Args:
        stations: List of station codes
        data_dir: Directory containing history files
        available_dates: List of recent dates to check for NEW anomalies
    """
    history_path = data_dir / ANOMALY_HISTORY_FILENAME
    entries = load_history_entries(history_path)
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
            
            is_anomalous = bool(station_data.get('is_anomalous') or station_data.get('isAnomalous'))
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
            
            # Check for earthquake correlation (14-30 days after anomaly)
            entry['has_correlated_eq'] = station_has_correlation(station_folder, event_date)
            
            entry_map[key] = entry
            updated = True
    
    # RETROACTIVE LINKING: Check all existing anomalies for new earthquakes
    # This handles cases where EQ occurs 14-30 days AFTER anomaly was detected
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
        new_status = station_has_correlation(station_folder, event_date)
        
        if old_status != new_status:
            entry['has_correlated_eq'] = new_status
            entry['last_confirmed'] = now_iso
            updated = True
            retroactive_updates += 1
    
    if retroactive_updates > 0:
        print(f'[INFO] Updated {retroactive_updates} anomalies with retroactive EQ correlations')
    
    if updated:
        sorted_entries = sorted(
            entry_map.values(),
            key=lambda e: (e.get('date', ''), e.get('station', ''))
        )
        save_history_entries(history_path, sorted_entries)
        
        # Count true positives and false positives
        true_positives = sum(1 for e in sorted_entries if e.get('has_correlated_eq'))
        false_positives = sum(1 for e in sorted_entries if not e.get('has_correlated_eq'))
        
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
    entries = load_history_entries(history_path)
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
                    entry_map[key] = entry
                    updated = True
        except Exception:
            continue
    if updated:
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
                        return data['stations']
                    elif isinstance(data['stations'], dict):
                        return list(data['stations'].keys())
        except Exception:
            pass
    
    # Last resort: raise error
    raise ValueError("No stations found. Please ensure data has been processed.")

def generate_aggregated_data_files(stations, available_dates, data_dir):
    """Generate aggregated JSON files per date for faster frontend loading
    
    Creates a single JSON file per date containing all station data, earthquake correlations,
    and metadata. This reduces frontend network requests from 100+ to 1 per date.
    
    Args:
        stations: List of station codes
        available_dates: List of dates to generate aggregated files for
        data_dir: Directory containing individual station JSON files
    
    Returns:
        Number of aggregated files generated
    """
    print('[INFO] Generating aggregated data files...')
    generated_count = 0
    
    # Load station metadata once
    metadata_dict = {}
    if Path('stations.json').exists():
        try:
            with open('stations.json', 'r', encoding='utf-8') as f:
                stations_metadata = json.load(f)
                
            # Handle different formats of stations.json
            if isinstance(stations_metadata, dict):
                if 'stations' in stations_metadata:
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
                    elif isinstance(stations_metadata['stations'], dict):
                        metadata_dict = stations_metadata['stations']
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
        except Exception as e:
            print(f'[WARNING] Could not load station metadata: {e}')
    
    # Generate aggregated file for each date
    for date in available_dates:
        aggregated_data = {
            'date': date,
            'generated_at': datetime.utcnow().isoformat(),
            'stations': {},
            'earthquake_correlations': {},
            'false_negatives': {},
            'metadata': metadata_dict
        }
        
        stations_with_data = 0
        
        # Collect data for each station
        for station in stations:
            # Try to load station JSON for this date
            station_json = data_dir / f'{station}_{date}.json'
            if station_json.exists():
                try:
                    with open(station_json, 'r', encoding='utf-8') as f:
                        station_data = json.load(f)
                    aggregated_data['stations'][station] = station_data
                    stations_with_data += 1
                except Exception as e:
                    print(f'[WARNING] Could not load {station_json.name}: {e}')
            
            # Load earthquake correlations CSV
            eq_corr_csv = data_dir / f'{station}_earthquake_correlations.csv'
            if eq_corr_csv.exists():
                try:
                    with open(eq_corr_csv, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        correlations = []
                        for row in reader:
                            # Filter by date and magnitude >= 5.0
                            anomaly_date = parse_any_date(
                                row.get('anomaly_date') or 
                                row.get('anomaly_date ') or 
                                row.get('anomalyDate')
                            )
                            if anomaly_date and anomaly_date.strftime('%Y-%m-%d') == date:
                                magnitude = safe_float(row.get('earthquake_magnitude') or row.get('magnitude'))
                                if magnitude is None or magnitude >= 5.0:
                                    correlations.append(dict(row))
                        
                        if correlations:
                            aggregated_data['earthquake_correlations'][station] = correlations
                except Exception as e:
                    print(f'[WARNING] Could not load {eq_corr_csv.name}: {e}')
            
            # Load false negatives CSV
            fn_csv = data_dir / f'{station}_false_negatives.csv'
            if fn_csv.exists():
                try:
                    with open(fn_csv, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        false_negs = [dict(row) for row in reader]
                        if false_negs:
                            aggregated_data['false_negatives'][station] = false_negs
                except Exception as e:
                    print(f'[WARNING] Could not load {fn_csv.name}: {e}')
        
        # Only save if we have data for at least one station
        if stations_with_data > 0:
            output_file = data_dir / f'aggregated_{date}.json'
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(aggregated_data, f, indent=2)
            
            file_size_kb = output_file.stat().st_size / 1024
            print(f'[INFO] Generated {output_file.name} ({stations_with_data} stations, {file_size_kb:.1f} KB)')
            generated_count += 1
        else:
            print(f'[WARNING] No data found for date {date}, skipping aggregated file')
    
    print(f'[INFO] Generated {generated_count} aggregated data files')
    return generated_count

def prepare_web_output():
    """Prepare static files for web deployment with date-specific handling"""
    print('Preparing web output...')
    
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
    
    # Create data and figures directories
    data_dir = OUTPUT_DIR / 'data'
    data_dir.mkdir(exist_ok=True)
    
    figures_dir = OUTPUT_DIR / 'figures'
    figures_dir.mkdir(exist_ok=True)
    
    # Get available dates (last 7 days)
    available_dates = get_available_dates()
    most_recent_date = available_dates[0] if available_dates else None
    
    print(f'[INFO] Available dates: {", ".join(available_dates)}')
    print(f'[INFO] Most recent date: {most_recent_date}')
    
    # Get stations
    stations = get_stations()
    
    # Copy date-specific files for the last 7 days
    cutoff_date = (datetime.now() - timedelta(days=6)).date()
    
    for station in stations:
        station_folder = Path('INTERMAGNET_DOWNLOADS') / station
        
        if not station_folder.exists():
            continue
        
        # Copy date-specific JSON files
        # Note: JSON files are named with "today's" date but contain data from yesterday 20:00 to today 04:00
        # So we need to create copies for both today and yesterday
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
                        
                        # Also create a copy for yesterday (since the JSON contains yesterday 20:00 to today 04:00)
                        yesterday_date_obj = file_date_obj - timedelta(days=1)
                        yesterday_date = yesterday_date_obj.strftime('%Y-%m-%d')
                        if yesterday_date_obj >= cutoff_date:  # Only if yesterday is also within range
                            dest_file_yesterday = data_dir / f'{station}_{yesterday_date}.json'
                            # Always copy/overwrite to ensure we have the latest data
                            shutil.copy(json_file, dest_file_yesterday)
                            print(f'[INFO] Created {station}_{yesterday_date}.json (from {file_date} data)')
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
    
    # Filter available_dates to only those that have aggregated files
    # This prevents the frontend from trying to load dates that failed generation (e.g. no data yet for today)
    valid_dates = []
    for date in available_dates:
        if (data_dir / f'aggregated_{date}.json').exists():
            valid_dates.append(date)
    
    if len(valid_dates) < len(available_dates):
        print(f'[INFO] Filtered available_dates from {len(available_dates)} to {len(valid_dates)} based on data availability')
        available_dates = valid_dates
        if available_dates:
            most_recent_date = available_dates[0]
        else:
            most_recent_date = None
    
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
