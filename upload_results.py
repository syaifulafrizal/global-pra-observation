#!/usr/bin/env python3
"""
Prepare processed results for local web serving
Prepares files in web_output/ directory for Flask to serve
Handles date-specific files and 7-day data retention
"""

import os
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
import shutil

# Configuration
OUTPUT_DIR = Path('web_output')  # Directory for prepared web files

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

def cleanup_old_files(data_dir, figures_dir, cutoff_date):
    """Remove files older than cutoff_date"""
    deleted_count = 0
    
    # Clean JSON files in data/
    if data_dir.exists():
        for json_file in data_dir.glob('*.json'):
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
    # Last resort: default to KAK
    return ['KAK']

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
        json_files = list(station_folder.glob('PRA_Night_*.json'))
        for json_file in json_files:
            file_date = parse_date_from_filename(json_file.name)
            if file_date and file_date in available_dates:
                try:
                    file_date_obj = datetime.strptime(file_date, '%Y-%m-%d').date()
                    if file_date_obj >= cutoff_date:
                        # Copy as {station}_{date}.json
                        dest_file = data_dir / f'{station}_{file_date}.json'
                        shutil.copy(json_file, dest_file)
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
    
    # Copy date-specific earthquake files
    for date in available_dates:
        eq_csv = Path(f'recent_earthquakes_{date}.csv')
        if eq_csv.exists():
            shutil.copy(eq_csv, data_dir / eq_csv.name)
    
    # Clean up old files (older than 6 days)
    deleted = cleanup_old_files(data_dir, figures_dir, cutoff_date)
    if deleted > 0:
        print(f'[INFO] Cleaned up {deleted} old files')
    
    # Load station metadata
    stations_metadata = {}
    if Path('stations.json').exists():
        try:
            with open('stations.json', 'r') as f:
                stations_metadata = json.load(f)
        except Exception:
            pass
    
    # Create stations.json with available dates and metadata
    stations_json = {
        'stations': stations,
        'available_dates': available_dates,
        'most_recent_date': most_recent_date,
        'last_updated': datetime.now().isoformat(),
    }
    
    # Add station metadata if available
    if isinstance(stations_metadata, dict) and 'stations' in stations_metadata:
        if isinstance(stations_metadata['stations'], dict):
            stations_json['metadata'] = stations_metadata['stations']
        elif isinstance(stations_metadata['stations'], list):
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
