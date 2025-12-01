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

def update_anomaly_history(stations, data_dir):
    """Append new anomalies to the persistent history log"""
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
    for station in stations:
        station_folder = Path('INTERMAGNET_DOWNLOADS') / station
        if not station_folder.exists():
            continue
        json_files = sorted(station_folder.glob('PRA_Night_*.json'))
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    station_data = json.load(f)
            except Exception:
                continue
            is_anomalous = bool(station_data.get('is_anomalous') or station_data.get('isAnomalous'))
            n_hours = station_data.get('nAnomHours') or station_data.get('n_anom_hours') or 0
            if not is_anomalous and (not n_hours or n_hours == 0):
                continue
            event_date = station_data.get('date') or parse_date_from_filename(json_file.name)
            if not event_date:
                continue
            key = f'{station}|{event_date}'
            entry = entry_map.get(key, {
                'station': station,
                'date': event_date,
                'first_detected': now_iso
            })
            entry['threshold'] = station_data.get('threshold')
            entry['n_anomaly_hours'] = n_hours
            entry['source_file'] = json_file.name
            entry['last_confirmed'] = now_iso
            entry['has_correlated_eq'] = station_has_correlation(station_folder, event_date)
            entry_map[key] = entry
            updated = True
    if updated:
        sorted_entries = sorted(
            entry_map.values(),
            key=lambda e: (e.get('date', ''), e.get('station', ''))
        )
        save_history_entries(history_path, sorted_entries)
        print(f'[INFO] Updated anomaly history with {len(sorted_entries)} total entries')
    else:
        # Ensure file exists even if no update occurred
        if not history_path.exists():
            sorted_entries = sorted(entries, key=lambda e: (e.get('date', ''), e.get('station', '')))
            save_history_entries(history_path, sorted_entries)
    return load_history_entries(history_path)

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
    return load_history_entries(history_path)

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
    update_anomaly_history(stations, data_dir)
    update_false_negative_history(stations, data_dir)
    
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
    return OUTPUT_DIR

def main():
    """Main function - prepare files for local serving"""
    print('='*60)
    print('PRA Results Preparation Script')
    print('='*60)
    
    # Prepare web output
    output_dir = prepare_web_output()
    
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
