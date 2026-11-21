"""Read-only v1 API envelopes around existing, unchanged observation snapshots."""
import json
import math
from pathlib import Path
import re

VERSION = '1.0'


def json_safe(value):
    """Represent missing numbers as JSON null without modifying recorded inputs."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def catalog(metadata):
    return {
        'schema_version': VERSION, 'name': 'GEMPRA observation API',
        'description': 'Completed nighttime observations. Dates are station-local night-end dates; recorded timestamps retain their source meaning.',
        'read_only': True, 'available_dates': metadata.get('available_dates', []),
        'latest_observation_date': metadata.get('most_recent_date'),
        'endpoints': {'status': 'status.json', 'stations': 'stations.json', 'latest': 'latest.json',
                      'observation': 'observations/{YYYY-MM-DD}.json',
                      'station_latest': 'stations/{CODE}/latest.json',
                      'station_observation': 'stations/{CODE}/{YYYY-MM-DD}.json'},
        'provenance': 'Thresholds, anomaly flags, actual dates and quality fields are the recorded pipeline outputs. A previous-night station fallback retains its actual date.',
    }


def status(metadata, snapshot):
    records = snapshot.get('stations', {})
    return {
        'schema_version': VERSION, 'updated_at': metadata.get('last_updated'),
        'latest_observation_date': metadata.get('most_recent_date'),
        'available_dates': metadata.get('available_dates', []),
        'station_count': len(metadata.get('stations', [])), 'usable_observations': len(records),
        'anomalies': [{'id': f'{code}|{record["date"]}', 'station': code,
                       'observation_date': record['date'], 'anomalous_hours': record.get('nAnomHours', 0)}
                      for code, record in sorted(records.items()) if record.get('is_anomalous') is True],
        'semantics': 'Anomaly observations are research signals, not earthquake predictions.',
    }


def payload(resource, metadata, load_snapshot):
    """Resolve only documented resources; never interpret a request as a file path."""
    dates = metadata.get('available_dates', [])
    if resource in ('', 'index.json'):
        return catalog(metadata)
    if resource == 'stations.json':
        return {'schema_version': VERSION, **metadata}
    if not dates:
        raise KeyError('No observation snapshots available')
    if resource == 'status.json':
        return status(metadata, load_snapshot(dates[0]))
    if resource == 'latest.json':
        return {'schema_version': VERSION, **load_snapshot(dates[0])}
    match = re.fullmatch(r'observations/(\d{4}-\d{2}-\d{2})\.json', resource)
    if match and match[1] in dates:
        return {'schema_version': VERSION, **load_snapshot(match[1])}
    match = re.fullmatch(r'stations/([A-Z0-9]{3})/(latest|\d{4}-\d{2}-\d{2})\.json', resource)
    if match and match[1] in metadata.get('stations', []):
        code, requested = match.groups()
        candidates = {}
        for day in dates:
            record = load_snapshot(day).get('stations', {}).get(code)
            if record:
                candidates[record['date']] = record
        actual = max(candidates) if requested == 'latest' and candidates else requested
        if actual in candidates:
            return {'schema_version': VERSION, 'station': code, 'observation_date': actual,
                    'metadata': metadata.get('metadata', {}).get(code, {}), 'observation': candidates[actual]}
    raise KeyError('Observation resource unavailable')


def export_api(folder, metadata):
    """Materialize the same resources for GitHub Pages, which serves static GETs."""
    folder = Path(folder)
    api = folder / 'api' / 'v1'
    dates = metadata.get('available_dates', [])
    snapshots = {day: json.loads((folder / 'data' / f'aggregated_{day}.json').read_text(encoding='utf-8'))
                 for day in dates}
    resources = {'index.json', 'stations.json', 'status.json', 'latest.json'}
    for day, snapshot in snapshots.items():
        resources.add(f'observations/{day}.json')
        for code, record in snapshot.get('stations', {}).items():
            resources.add(f'stations/{code}/latest.json')
            resources.add(f'stations/{code}/{record["date"]}.json')
    for resource in sorted(resources):
        content = payload(resource, metadata, snapshots.__getitem__)
        target = api / resource
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(json_safe(content), indent=2, allow_nan=False), encoding='utf-8')
    return len(resources)
