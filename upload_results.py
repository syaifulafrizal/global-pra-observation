#!/usr/bin/env python3
"""
Prepare processed results for local web serving
Prepares files in web_output/ directory for Flask to serve
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta
import shutil
import re

# Configuration
OUTPUT_DIR = Path('web_output')  # Directory for prepared web files

def get_stations():
    """Get list of stations - auto-detect from processed data or use env var"""
    stations_env = os.getenv('INTERMAGNET_STATIONS', '')
    if stations_env:
        return [s.strip() for s in stations_env.split(',')]
    
    # Priority 1: Auto-detect from INTERMAGNET_DOWNLOADS (source of truth)
    downloads_dir = Path('INTERMAGNET_DOWNLOADS')
    if downloads_dir.exists():
        stations = []
        for station_dir in downloads_dir.iterdir():
            if station_dir.is_dir() and not station_dir.name.startswith('.') and not station_dir.name.startswith('_'):
                # Check if this station has processed JSON files
                json_files = list(station_dir.glob('PRA_Night_*.json'))
                if json_files:
                    stations.append(station_dir.name)
        
        if stations:
            stations.sort()
            print(f'[INFO] Auto-detected {len(stations)} processed stations from INTERMAGNET_DOWNLOADS')
            return stations
    
    # Priority 2: Check web_output/data for existing _latest.json files
    # (fallback if INTERMAGNET_DOWNLOADS doesn't exist)
    web_data_dir = Path('web_output') / 'data'
    if web_data_dir.exists():
        json_files = list(web_data_dir.glob('*_latest.json'))
        if json_files:
            stations = sorted([f.stem.replace('_latest', '') for f in json_files])
            print(f'[INFO] Found {len(stations)} stations from web_output/data (fallback)')
            return stations
    
    # Priority 3: Try to load from existing web_output/data/stations.json
    web_stations_json = Path('web_output') / 'data' / 'stations.json'
    if web_stations_json.exists():
        try:
            with open(web_stations_json, 'r') as f:
                data = json.load(f)
                if isinstance(data, dict) and 'stations' in data:
                    if isinstance(data['stations'], list) and len(data['stations']) > 1:
                        print(f'[INFO] Using {len(data["stations"])} stations from existing web_output/data/stations.json')
                        return data['stations']
        except Exception:
            pass
    
    # Priority 4: Try to load from root stations.json
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
    
    # Last resort: raise error instead of defaulting
    raise ValueError(
        "ERROR: Could not detect any stations!\n"
        "Please ensure:\n"
        "  1. INTERMAGNET_DOWNLOADS/ contains processed station folders with PRA_Night_*.json files\n"
        "  2. Or set INTERMAGNET_STATIONS environment variable\n"
        "  3. Or ensure stations.json exists in the project root\n"
        "This error prevents using a default station to avoid incorrect results."
    )

def parse_date_from_filename(filename):
    """Extract date from PRA_Night_{station}_{YYYYMMDD}.json filename"""
    # Pattern: PRA_Night_{station}_{YYYYMMDD}.json
    match = re.search(r'PRA_Night_\w+_(\d{8})\.json', filename)
    if match:
        date_str = match.group(1)
        try:
            return datetime.strptime(date_str, '%Y%m%d').date()
        except ValueError:
            return None
    return None

def get_available_dates():
    """Get list of available dates (last 7 days including today)"""
    today = datetime.now().date()
    dates = []
    for i in range(7):
        date = today - timedelta(days=i)
        dates.append(date.strftime('%Y-%m-%d'))
    return dates

def cleanup_old_files(data_dir, cutoff_date):
    """Delete files older than cutoff_date from web_output/data"""
    deleted_count = 0
    for file_path in data_dir.glob('*_*.json'):
        if file_path.name == 'stations.json':
            continue
        
        # Try to extract date from filename (format: {station}_{YYYY-MM-DD}.json)
        match = re.search(r'_\d{4}-\d{2}-\d{2}\.json$', file_path.name)
        if match:
            date_str = match.group(0)[1:-5]  # Remove _ and .json
            try:
                file_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                if file_date < cutoff_date:
                    file_path.unlink()
                    deleted_count += 1
            except ValueError:
                pass
    
    # Also clean up old figure files
    figures_dir = OUTPUT_DIR / 'figures'
    if figures_dir.exists():
        for station_dir in figures_dir.iterdir():
            if station_dir.is_dir():
                for fig_file in station_dir.glob('PRA_*.png'):
                    # Extract date from filename: PRA_{station}_{YYYYMMDD}.png
                    match = re.search(r'_(\d{8})\.png$', fig_file.name)
                    if match:
                        date_str = match.group(1)
                        try:
                            file_date = datetime.strptime(date_str, '%Y%m%d').date()
                            if file_date < cutoff_date:
                                fig_file.unlink()
                                deleted_count += 1
                        except ValueError:
                            pass
    
    if deleted_count > 0:
        print(f'[INFO] Deleted {deleted_count} old files (older than {cutoff_date})')
    return deleted_count

def prepare_web_output():
    """Prepare static files for web deployment with 7-day retention"""
    print('Preparing web output...')
    
    # Calculate cutoff date (6 days ago, so we keep 7 days total)
    today = datetime.now().date()
    cutoff_date = today - timedelta(days=6)
    
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
    
    # Create data directory
    data_dir = OUTPUT_DIR / 'data'
    data_dir.mkdir(exist_ok=True)
    
    # Clean up old files first
    cleanup_old_files(data_dir, cutoff_date)
    
    # Copy stations.json for map metadata
    if Path('stations.json').exists():
        shutil.copy('stations.json', data_dir / 'stations.json')
    
    stations = get_stations()
    all_available_dates = set()
    date_station_data = {}  # {date: {station: data}}
    
    # Process each station
    for station in stations:
        station_folder = Path('INTERMAGNET_DOWNLOADS') / station
        
        if station_folder.exists():
            # Get all JSON files for this station
            json_files = list(station_folder.glob('PRA_Night_*.json'))
            
            for json_file in json_files:
                # Extract date from filename
                file_date = parse_date_from_filename(json_file.name)
                if file_date is None:
                    continue
                
                # Only keep files from last 7 days
                if file_date < cutoff_date:
                    continue
                
                # Format date as YYYY-MM-DD
                date_str = file_date.strftime('%Y-%m-%d')
                all_available_dates.add(date_str)
                
                # Copy JSON file with date-specific name
                dest_file = data_dir / f'{station}_{date_str}.json'
                shutil.copy(json_file, dest_file)
                
                # Load data for this date
                if date_str not in date_station_data:
                    date_station_data[date_str] = {}
                
                with open(json_file, 'r') as f:
                    date_station_data[date_str][station] = json.load(f)
        
        # Copy anomaly table (only latest, not date-specific)
        anomaly_file = station_folder / 'anomaly_master_table.csv'
        if anomaly_file.exists():
            shutil.copy(anomaly_file, data_dir / f'{station}_anomalies.csv')
        
        # Copy earthquake correlations if available
        eq_file = station_folder / 'earthquake_correlations.csv'
        if eq_file.exists():
            shutil.copy(eq_file, data_dir / f'{station}_earthquake_correlations.csv')
        
        # Copy false negatives if available
        fn_file = station_folder / 'false_negatives.csv'
        if fn_file.exists():
            shutil.copy(fn_file, data_dir / f'{station}_false_negatives.csv')
        
        # Copy figures (only last 7 days)
        figures_dir = station_folder / 'figures'
        if figures_dir.exists():
            web_figures_dir = OUTPUT_DIR / 'figures' / station
            web_figures_dir.mkdir(parents=True, exist_ok=True)
            
            # Get all figure files
            figures = list(figures_dir.glob('PRA_*.png'))
            for fig in figures:
                # Extract date from filename: PRA_{station}_{YYYYMMDD}.png
                match = re.search(r'_(\d{8})\.png$', fig.name)
                if match:
                    date_str = match.group(1)
                    try:
                        fig_date = datetime.strptime(date_str, '%Y%m%d').date()
                        if fig_date >= cutoff_date:
                            shutil.copy(fig, web_figures_dir / fig.name)
                    except ValueError:
                        pass
    
    # Get available dates sorted (most recent first)
    available_dates = sorted(all_available_dates, reverse=True)
    
    # Get most recent date
    most_recent_date = available_dates[0] if available_dates else None
    
    # Get data for most recent date (for backward compatibility)
    most_recent_data = date_station_data.get(most_recent_date, {}) if most_recent_date else {}
    
    # Create stations index JSON (combine with metadata)
    stations_metadata = {}
    if Path('stations.json').exists():
        with open('stations.json', 'r') as f:
            stations_metadata = json.load(f)
    
    # Create combined stations.json for frontend
    with open(data_dir / 'stations.json', 'w') as f:
        json.dump({
            'stations': stations,
            'last_updated': datetime.now().isoformat(),
            'available_dates': available_dates,  # List of available dates (most recent first)
            'most_recent_date': most_recent_date,  # Default date to show
            'data': most_recent_data,  # Data for most recent date (default)
            'metadata': stations_metadata.get('stations', []) if isinstance(stations_metadata, dict) else []
        }, f, indent=2)
    
    print(f'[INFO] Available dates: {", ".join(available_dates)}')
    print(f'[INFO] Most recent date: {most_recent_date}')
    
    # Copy index.html
    if Path('templates/index.html').exists():
        # Create a static version (without Flask template syntax)
        create_static_index(OUTPUT_DIR, stations, most_recent_data)
    else:
        # Create basic index.html
        create_basic_index(OUTPUT_DIR, stations)
    
    print(f'[OK] Web output prepared in {OUTPUT_DIR}')
    return OUTPUT_DIR

def create_static_index(output_dir, stations, stations_data):
    """Create static HTML index file"""
    # Create static HTML (JavaScript will populate data)
    html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PRA Nighttime Detection - Dashboard</title>
    <link rel="stylesheet" href="static/style.css">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body>
    <div class="container">
        <header>
            <h1>🌍 PRA Nighttime Detection Dashboard</h1>
            <p class="subtitle">Polarization Ratio Analysis for INTERMAGNET Stations</p>
            <div class="header-controls">
                <div class="date-selector-container">
                    <label for="date-selector" style="color: #ecf0f1; margin-right: 10px; font-weight: 500;">Select Date:</label>
                    <select id="date-selector" style="padding: 8px 12px; font-size: 1em; border-radius: 4px; border: 1px solid #34495e; background: #2c3e50; color: #ecf0f1; cursor: pointer;">
                        <option value="">Loading dates...</option>
                    </select>
                </div>
                <p class="timestamp">Last updated: <span id="timestamp">Loading...</span></p>
            </div>
        </header>

        <div id="stations-container">
            <p>Loading data...</p>
        </div>

        <footer>
            <p class="method-info">
                Method: Multitaper Spectral Analysis (NW=3.5) + Extreme Value Theory (EVT) + nZ Normalization<br>
                Frequency Band: 0.095-0.110 Hz | Time Window: 20:00-04:00 Local Time
            </p>
            
            <div class="acknowledgements">
                <h3>Acknowledgements</h3>
                <ul>
                    <li>Data provided by <a href="https://www.intermagnet.org" target="_blank">INTERMAGNET</a> (International Real-time Magnetic Observatory Network)</li>
                    <li>Earthquake data from <a href="https://earthquake.usgs.gov" target="_blank">USGS</a> (United States Geological Survey)</li>
                    <li>SYM-H index data from <a href="https://omniweb.gsfc.nasa.gov" target="_blank">NASA OMNIWeb</a></li>
                    <li>Research conducted at <a href="https://www.upm.edu.my" target="_blank">Universiti Putra Malaysia</a></li>
                </ul>
            </div>
            
            <div class="author">
                <p>Developed by <a href="https://github.com/syaifulafrizal" target="_blank">Nur Syaiful Afrizal</a></p>
            </div>
        </footer>
    </div>

    <script src="static/app.js"></script>
</body>
</html>'''
    
    with open(output_dir / 'index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)

def create_basic_index(output_dir, stations):
    """Create basic index.html if template doesn't exist"""
    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PRA Nighttime Detection</title>
    <link rel="stylesheet" href="static/style.css">
</head>
<body>
    <div class="container">
        <header>
            <h1>🌍 PRA Nighttime Detection Dashboard</h1>
            <p class="subtitle">Polarization Ratio Analysis for INTERMAGNET Stations</p>
        </header>
        <div id="stations-container" class="stations-grid">
            <p>Loading data...</p>
        </div>
    </div>
    <script src="static/app.js"></script>
</body>
</html>'''
    
    with open(output_dir / 'index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)


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

