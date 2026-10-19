#!/usr/bin/env python3
"""Export the local read-only dashboard to a new, unpublished static folder."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from app import app


def build_preview(destination):
    """Use the same Flask snapshots as the reviewed UI; preserve all inputs."""
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f'Choose a new output directory: {destination}')
    destination.mkdir(parents=True)
    data_dir = destination / 'data'
    data_dir.mkdir()
    shutil.copytree('static', destination / 'static')
    (destination / '.nojekyll').write_text('', encoding='utf-8')
    written_figures = set()

    def save_response(client, route, path):
        with client.get(route) as response:
            if response.status_code != 200:
                return False
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.data)
            return True

    with app.test_client() as client:
        save_response(client, '/', destination / 'index.html')
        metadata = client.get('/data/stations.json').get_json()
        if not metadata or not metadata.get('stations'):
            raise ValueError('No station snapshots available for preview')
        (data_dir / 'stations.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        for name in ('anomaly_history.json', 'false_negative_history.json'):
            save_response(client, f'/data/{name}', data_dir / name)
        for date in metadata['available_dates']:
            response = client.get(f'/data/aggregated_{date}.json')
            snapshot = response.get_json()
            response.close()
            (data_dir / f'aggregated_{date}.json').write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
            for name in (f'earthquake_stats_{date}.json', f'recent_earthquakes_{date}.csv'):
                save_response(client, f'/data/{name}', data_dir / name)
            for station, result in snapshot['stations'].items():
                actual_date = result['date']
                (data_dir / f'{station}_{actual_date}.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
                figure = f'{station}/PRA_{station}_{actual_date.replace("-", "")}.png'
                if figure not in written_figures:
                    save_response(client, f'/figures/{figure}', destination / 'figures' / figure)
                    written_figures.add(figure)

    manifest = {
        'publication_status': 'unpublished_preview',
        'observation_dates': metadata['available_dates'],
        'stations': len(metadata['stations']),
        'source_files': {},
    }
    for name in ('templates/index.html', 'static/style.css', 'static/app.js',
                 'static/assets/gempra-field-emblem.png',
                 'static/assets/gempra-emblem-96.png', 'static/assets/gempra-favicon-32.png'):
        manifest['source_files'][name] = hashlib.sha256(Path(name).read_bytes()).hexdigest()
    (destination / 'preview-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('output/site-preview'))
    arguments = parser.parse_args()
    result = build_preview(arguments.output)
    print(f'Unpublished preview: {arguments.output.resolve()}')
    print(f'{result["stations"]} stations; {len(result["observation_dates"])} dates')
