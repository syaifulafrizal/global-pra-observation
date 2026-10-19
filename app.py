#!/usr/bin/env python3
"""
Flask web application for PRA Nighttime Detection
Local testing interface
"""

from flask import Flask, render_template, jsonify, send_from_directory
from pathlib import Path
import json
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
from snapshot_cache import SnapshotCache, file_revisions

_metadata_cache = SnapshotCache(max_entries=2, max_bytes=1024 * 1024)
_snapshot_cache = SnapshotCache()

app = Flask(__name__, static_folder=None)

# Serve static files from web_output/static
@app.route('/static/<path:filename>')
def serve_static(filename):
    # Local HTML and assets always come from the same source version.
    source_static = Path(app.root_path) / 'static'
    if (source_static / filename).is_file():
        return send_from_directory(str(source_static), filename)
    return send_from_directory('web_output/static', filename)

# Serve data files from web_output/data
@app.route('/data/<path:filename>')
def serve_data_file(filename):
    """Serve data files - tries web_output first, then source directories"""
    # Build current local snapshots in memory; existing prepared files are
    # preserved and remain available as a compatibility fallback.
    from upload_results import (build_aggregated_data, merge_history,
                                station_correlation_status)
    if filename == 'stations.json':
        metadata = local_metadata()
        if metadata['stations']:
            return jsonify(metadata)
    import re
    match = re.fullmatch(r'aggregated_(\d{4}-\d{2}-\d{2})\.json', filename)
    if match:
        metadata = local_metadata()
    if match and metadata['stations']:
        try:
            source = Path('INTERMAGNET_DOWNLOADS')
            dependencies = [Path('stations.json')]
            day = match.group(1)
            previous_day = (datetime.strptime(day, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y%m%d')
            for station in metadata['stations']:
                folder = source / station
                dependencies.extend([folder / f'PRA_Night_{station}_{day.replace("-", "")}.json',
                                     folder / f'PRA_Night_{station}_{previous_day}.json',
                                     folder / 'earthquake_correlations.csv', folder / 'false_negatives.csv'])
            revision = (file_revisions(dependencies), tuple(metadata['stations']))
            snapshot = _snapshot_cache.get((str(Path.cwd()), match.group(1)), revision,
                lambda: build_aggregated_data(metadata['stations'], match.group(1),
                    Path('web_output/data'), source_folder=source))
        except ValueError:
            return 'Invalid date', 404
        return jsonify(snapshot)
    if filename in ('anomaly_history.json', 'false_negative_history.json'):
        keys = ('station', 'date') if filename == 'anomaly_history.json' else ('station', 'earthquake_time')
        entries = merge_history(Path('web_output/data') / filename, Path('data/history') / filename, keys)
        if filename == 'anomaly_history.json':
            for entry in entries:
                entry['status'] = station_correlation_status(
                    Path('INTERMAGNET_DOWNLOADS') / entry['station'], entry['date'])
                entry['has_correlated_eq'] = entry['status'] == 'TP'
        return jsonify({'entries': entries})
    match = re.fullmatch(r'([A-Z0-9]{3})_(\d{4}-\d{2}-\d{2})\.json', filename)
    if match:
        from result_validation import result_is_usable
        station, day = match.groups()
        path = Path('INTERMAGNET_DOWNLOADS') / station / f'PRA_Night_{station}_{day.replace("-", "")}.json'
        if path.exists():
            result = json.loads(path.read_text(encoding='utf-8'))
            if result.get('date') == day and result_is_usable(result):
                return jsonify(result)
            return 'Station data unavailable or invalid', 404
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

def local_metadata():
    dependencies = list(Path('INTERMAGNET_DOWNLOADS').glob('*/PRA_Night_*.json'))
    dependencies.append(Path('stations.json'))
    revision = (file_revisions(dependencies), os.getenv('INTERMAGNET_STATIONS', ''))
    return _metadata_cache.get(str(Path.cwd()), revision, _discover_metadata)


def _discover_metadata():
    """Discover canonical result dates without regenerating or deleting files."""
    from upload_results import load_station_metadata
    import re
    stations = set()
    dates = set()
    latest_mtime = 0
    selected = {code.strip() for code in os.getenv('INTERMAGNET_STATIONS', '').split(',') if code.strip()}
    for path in Path('INTERMAGNET_DOWNLOADS').glob('*/PRA_Night_*.json'):
        station = path.parent.name
        if selected and station not in selected:
            continue
        match = re.search(r'_(\d{8})\.json$', path.name)
        if not match:
            continue
        try:
            day = datetime.strptime(match.group(1), '%Y%m%d').date().isoformat()
        except ValueError:
            continue
        stations.add(station)
        dates.add(day)
        latest_mtime = max(latest_mtime, path.stat().st_mtime)
    available = sorted(dates, reverse=True)[:7]
    return {'stations': sorted(stations), 'available_dates': available,
            'most_recent_date': available[0] if available else None,
            'last_updated': datetime.fromtimestamp(latest_mtime, ZoneInfo('UTC')).isoformat() if latest_mtime else None,
            'metadata': load_station_metadata()}


def get_stations():
    stations_env = os.getenv('INTERMAGNET_STATIONS', '')
    if stations_env:
        return [s.strip() for s in stations_env.split(',') if s.strip()]
    return local_metadata()['stations'] or ['KAK']


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
    """Serve the current source template alongside the current source assets."""
    return render_template('index.html')


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
    source_folder = Path('INTERMAGNET_DOWNLOADS') / station_code / 'figures'
    if (source_folder / filename).is_file():
        return send_from_directory(str(source_folder), filename)
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
    return serve_data_file(filename)


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
    print('   Local snapshots are also assembled in memory without changing saved data')
    print('='*60)
    print()
    
    app.run(debug=True, host='0.0.0.0', port=5000)

