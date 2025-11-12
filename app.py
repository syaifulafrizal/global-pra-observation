#!/usr/bin/env python3
"""
Flask web application for PRA Nighttime Detection
Local testing interface
"""

from flask import Flask, render_template, jsonify, send_from_directory
from pathlib import Path
import json
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
import os

app = Flask(__name__)

# Serve static files from web_output/static
@app.route('/static/<path:filename>')
def serve_static(filename):
    # Try web_output first
    web_static = Path('web_output') / 'static' / filename
    if web_static.exists():
        return send_from_directory('web_output/static', filename)
    # Fallback to source static
    return send_from_directory('static', filename)

# Serve data files from web_output/data
@app.route('/data/<path:filename>')
def serve_data_file(filename):
    """Serve data files - tries web_output first, then source directories"""
    # Try web_output first (prepared files)
    web_data = Path('web_output') / 'data' / filename
    if web_data.exists():
        return send_from_directory('web_output/data', filename)
    
    # Fallback: serve directly from source directories
    data_folder = Path('INTERMAGNET_DOWNLOADS')
    
    # Handle stations.json (metadata)
    if filename == 'stations.json':
        stations_json = Path('stations.json')
        if stations_json.exists():
            return send_from_directory('.', 'stations.json')
    
    # Handle station-specific files
    if filename.endswith('_latest.json'):
        station = filename.replace('_latest.json', '')
        json_file = data_folder / station / f'PRA_Night_{station}_*.json'
        import glob
        files = glob.glob(str(json_file))
        if files:
            latest = max(files, key=lambda p: Path(p).stat().st_mtime)
            return send_from_directory(str(Path(latest).parent), Path(latest).name)
    elif filename.endswith('_anomalies.csv'):
        station = filename.replace('_anomalies.csv', '')
        anomaly_file = data_folder / station / 'anomaly_master_table.csv'
        if anomaly_file.exists():
            return send_from_directory(str(anomaly_file.parent), 'anomaly_master_table.csv')
    elif filename.endswith('_earthquake_correlations.csv'):
        station = filename.replace('_earthquake_correlations.csv', '')
        eq_file = data_folder / station / 'earthquake_correlations.csv'
        if eq_file.exists():
            return send_from_directory(str(eq_file.parent), 'earthquake_correlations.csv')
    
    return "Data not found", 404

# Serve figures from web_output/figures
@app.route('/figures/<path:filename>')
def serve_figure_file(filename):
    """Serve figure files"""
    # Try web_output first (for static deployment)
    web_fig = Path('web_output') / 'figures' / filename
    if web_fig.exists():
        return send_from_directory('web_output/figures', filename)
    
    # Fallback to local folder
    fig_folder = Path('INTERMAGNET_DOWNLOADS')
    parts = filename.split('/')
    if len(parts) == 2:
        station, fig_name = parts
        fig_file = fig_folder / station / 'figures' / fig_name
        if fig_file.exists():
            return send_from_directory(str(fig_file.parent), fig_name)
    
    return "Figure not found", 404

TZ = ZoneInfo('Asia/Tokyo')
RUN_TIMEZONE = ZoneInfo('Asia/Singapore')

def get_stations():
    """Get list of stations"""
    stations_env = os.getenv('INTERMAGNET_STATIONS', '')
    if stations_env:
        return [s.strip() for s in stations_env.split(',')]
    return ['KAK']

def get_latest_results(station_code):
    """Get latest results for a station"""
    data_folder = Path('INTERMAGNET_DOWNLOADS') / station_code
    
    # Find latest JSON file
    json_files = list(data_folder.glob('PRA_Night_*.json'))
    if not json_files:
        return None
    
    latest_file = max(json_files, key=lambda p: p.stat().st_mtime)
    
    with open(latest_file, 'r') as f:
        return json.load(f)

def get_anomaly_table(station_code):
    """Get anomaly master table"""
    log_file = Path('INTERMAGNET_DOWNLOADS') / station_code / 'anomaly_master_table.csv'
    if not log_file.exists():
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(log_file)
        # Sort by date (most recent first)
        if 'Range' in df.columns:
            df['_sort_date'] = df['Range'].str.split().str[0]
            df = df.sort_values('_sort_date', ascending=False, na_position='last')
            df = df.drop('_sort_date', axis=1)
        return df.head(10)  # Last 10 anomalies
    except:
        return pd.DataFrame()

def get_figures(station_code, limit=5):
    """Get list of recent figures"""
    fig_folder = Path('INTERMAGNET_DOWNLOADS') / station_code / 'figures'
    if not fig_folder.exists():
        return []
    
    figures = list(fig_folder.glob('PRA_*.png'))
    figures.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [f.name for f in figures[:limit]]

@app.route('/')
def index():
    """Main page - serve static HTML from web_output"""
    # Serve from web_output if it exists (prepared by upload_results.py)
    static_index = Path('web_output') / 'index.html'
    if static_index.exists():
        return send_from_directory('web_output', 'index.html')
    
    # If web_output doesn't exist, prepare it automatically
    print('[INFO] web_output/ not found, preparing files...')
    try:
        from upload_results import prepare_web_output
        prepare_web_output()
        if static_index.exists():
            return send_from_directory('web_output', 'index.html')
    except Exception as e:
        print(f'[WARNING] Could not prepare web_output: {e}')
    
    # Final fallback: use template (if exists)
    stations = get_stations()
    station_data = {}
    
    for station in stations:
        results = get_latest_results(station)
        anomalies = get_anomaly_table(station)
        figures = get_figures(station)
        
        station_data[station] = {
            'results': results,
            'anomalies': anomalies.to_dict('records') if not anomalies.empty else [],
            'figures': figures,
            'has_data': results is not None
        }
    
    return render_template('index.html', stations=stations, station_data=station_data)

@app.route('/api/stations')
def api_stations():
    """API: Get list of stations"""
    return jsonify(get_stations())

@app.route('/api/results/<station_code>')
def api_results(station_code):
    """API: Get latest results for a station"""
    results = get_latest_results(station_code)
    if results:
        return jsonify(results)
    return jsonify({'error': 'No results found'}), 404

@app.route('/api/anomalies/<station_code>')
def api_anomalies(station_code):
    """API: Get anomalies for a station"""
    anomalies = get_anomaly_table(station_code)
    if not anomalies.empty:
        return jsonify(anomalies.to_dict('records'))
    return jsonify([])

@app.route('/figures/<station_code>/<filename>')
def serve_figure(station_code, filename):
    """Serve figure files"""
    # Try web_output first (for static deployment)
    web_fig = Path('web_output') / 'figures' / station_code / filename
    if web_fig.exists():
        return send_from_directory(str(web_fig.parent), filename)
    
    # Fallback to local folder
    fig_folder = Path('INTERMAGNET_DOWNLOADS') / station_code / 'figures'
    if fig_folder.exists():
        return send_from_directory(str(fig_folder), filename)
    
    return "Figure not found", 404

@app.route('/data/<filename>')
def serve_data(filename):
    """Serve data files - tries web_output first, then source directories"""
    # Try web_output first (prepared files)
    web_data = Path('web_output') / 'data' / filename
    if web_data.exists():
        return send_from_directory(str(web_data.parent), filename)
    
    # Fallback: serve directly from source directories
    data_folder = Path('INTERMAGNET_DOWNLOADS')
    
    # Handle stations.json (metadata)
    if filename == 'stations.json':
        stations_json = Path('stations.json')
        if stations_json.exists():
            return send_from_directory('.', 'stations.json')
    
    # Handle station-specific files
    if filename.endswith('_latest.json'):
        station = filename.replace('_latest.json', '')
        json_file = data_folder / station / f'PRA_Night_{station}_*.json'
        import glob
        files = glob.glob(str(json_file))
        if files:
            latest = max(files, key=lambda p: Path(p).stat().st_mtime)
            return send_from_directory(str(Path(latest).parent), Path(latest).name)
    elif filename.endswith('_anomalies.csv'):
        station = filename.replace('_anomalies.csv', '')
        anomaly_file = data_folder / station / 'anomaly_master_table.csv'
        if anomaly_file.exists():
            return send_from_directory(str(anomaly_file.parent), 'anomaly_master_table.csv')
    elif filename.endswith('_earthquake_correlations.csv'):
        station = filename.replace('_earthquake_correlations.csv', '')
        eq_file = data_folder / station / 'earthquake_correlations.csv'
        if eq_file.exists():
            return send_from_directory(str(eq_file.parent), 'earthquake_correlations.csv')
    
    return "Data not found", 404

if __name__ == '__main__':
    # Create necessary directories
    Path('templates').mkdir(exist_ok=True)
    Path('static').mkdir(exist_ok=True)
    Path('web_output').mkdir(exist_ok=True)
    
    print('='*60)
    print('PRA Nighttime Detection - Local Web Server')
    print('='*60)
    print('\nStarting Flask server...')
    print('Dashboard will be available at: http://localhost:5000')
    print('\nTip: Run "python upload_results.py" first to prepare files')
    print('   (or Flask will prepare them automatically on first load)')
    print('='*60)
    print()
    
    app.run(debug=True, host='0.0.0.0', port=5000)

