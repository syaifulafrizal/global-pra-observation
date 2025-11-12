#!/usr/bin/env python3
"""
Prepare processed results for local web serving
Prepares files in web_output/ directory for Flask to serve
"""

import os
import json
from pathlib import Path
from datetime import datetime
import shutil

# Configuration
OUTPUT_DIR = Path('web_output')  # Directory for prepared web files

def get_stations():
    """Get list of stations"""
    stations_env = os.getenv('INTERMAGNET_STATIONS', '')
    if stations_env:
        return [s.strip() for s in stations_env.split(',')]
    return ['KAK']

def prepare_web_output():
    """Prepare static files for web deployment"""
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
    
    # Create data directory
    data_dir = OUTPUT_DIR / 'data'
    data_dir.mkdir(exist_ok=True)
    
    # Copy stations.json for map metadata
    if Path('stations.json').exists():
        shutil.copy('stations.json', data_dir / 'stations.json')
    
    stations = get_stations()
    all_stations_data = {}
    
    for station in stations:
        station_folder = Path('INTERMAGNET_DOWNLOADS') / station
        
        if not station_folder.exists():
            continue
        
        # Copy latest JSON results
        json_files = list(station_folder.glob('PRA_Night_*.json'))
        if json_files:
            latest_json = max(json_files, key=lambda p: p.stat().st_mtime)
            shutil.copy(latest_json, data_dir / f'{station}_latest.json')
            
            # Load and add to all_stations_data
            with open(latest_json, 'r') as f:
                all_stations_data[station] = json.load(f)
        
        # Copy anomaly table
        anomaly_file = station_folder / 'anomaly_master_table.csv'
        if anomaly_file.exists():
            shutil.copy(anomaly_file, data_dir / f'{station}_anomalies.csv')
        
        # Copy earthquake correlations if available
        eq_file = station_folder / 'earthquake_correlations.csv'
        if eq_file.exists():
            shutil.copy(eq_file, data_dir / f'{station}_earthquake_correlations.csv')
        
        # Copy figures
        figures_dir = station_folder / 'figures'
        if figures_dir.exists():
            web_figures_dir = OUTPUT_DIR / 'figures' / station
            web_figures_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy latest 10 figures
            figures = sorted(figures_dir.glob('*.png'), key=lambda p: p.stat().st_mtime, reverse=True)[:10]
            for fig in figures:
                shutil.copy(fig, web_figures_dir / fig.name)
    
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
            'data': all_stations_data,
            'metadata': stations_metadata.get('stations', []) if isinstance(stations_metadata, dict) else []
        }, f, indent=2)
    
    # Copy index.html
    if Path('templates/index.html').exists():
        # Create a static version (without Flask template syntax)
        create_static_index(OUTPUT_DIR, stations, all_stations_data)
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
            <p class="timestamp">Last updated: <span id="timestamp">Loading...</span></p>
        </header>

        <div id="stations-container">
            <p>Loading data...</p>
        </div>

        <footer>
            <p>Method: Multitaper (NW=3.5) + EVT + nZ z-score | 
               Frequency Band: 0.095-0.110 Hz | 
               Time Window: 20:00-04:00 Local Time</p>
            <p><a href="https://github.com/syaifulafrizal">Nur Syaiful Afrizal</a></p>
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

