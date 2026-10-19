#!/usr/bin/env python3
"""Read-only publication gate for the actual daily export, before Git is touched."""
import json
from pathlib import Path
import sys
from result_validation import result_is_usable


def validate_pages_output(folder):
    folder = Path(folder)
    for name in ('index.html', 'static/app.js', 'static/style.css'):
        (folder / name).read_text(encoding='utf-8')
    metadata = json.loads((folder / 'data/stations.json').read_text(encoding='utf-8-sig'))
    dates = metadata.get('available_dates', [])
    if not dates or dates != sorted(set(dates), reverse=True):
        raise ValueError('Available dates must be nonempty, unique and newest first')
    if metadata.get('most_recent_date') != dates[0]:
        raise ValueError('Default date must match the latest available observation')
    for day in dates:
        path = folder / 'data' / f'aggregated_{day}.json'
        if not path.is_file():
            raise ValueError(f'Advertised date {day} has no aggregate file')
        snapshot = json.loads(path.read_text(encoding='utf-8-sig'))
        stations = snapshot.get('stations', {})
        if not stations or not any(result.get('date') == day and result_is_usable(result)
                                   for result in stations.values()):
            raise ValueError(f'Advertised date {day} has no usable observations for that night')
        if any(not result_is_usable(result) for result in stations.values()):
            raise ValueError(f'Aggregate {day} contains invalid observations')
    return {'dates': dates, 'latest': dates[0], 'stations': len(metadata.get('stations', []))}


if __name__ == '__main__':
    try:
        result = validate_pages_output(sys.argv[1] if len(sys.argv) > 1 else 'web_output')
        print(f'Publication validated: latest {result["latest"]}; {len(result["dates"])} observation dates')
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f'Publication blocked: {error}', file=sys.stderr)
        sys.exit(1)
