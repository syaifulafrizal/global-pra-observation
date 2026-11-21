"""Read-only API contracts, snapshot provenance and portable export checks."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import public_api as api
import app as server


class PublicApiTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {'stations': ['KAK'], 'available_dates': ['2026-11-21', '2026-11-20'],
                         'most_recent_date': '2026-11-21', 'metadata': {'KAK': {'timezone': 'Asia/Tokyo'}}}
        self.record = {'date': '2026-11-20', 'P': [1.2, None], 'threshold': 2.4,
                       'is_anomalous': True, 'nAnomHours': 1}
        self.snapshots = {day: {'date': day, 'stations': {'KAK': self.record}}
                          for day in self.metadata['available_dates']}

    def test_actual_dates_and_recorded_numbers_survive_wrapping(self):
        result = api.payload('stations/KAK/latest.json', self.metadata, self.snapshots.__getitem__)
        self.assertEqual(result['observation'], self.record)
        self.assertEqual(result['observation_date'], '2026-11-20')
        status = api.payload('status.json', self.metadata, self.snapshots.__getitem__)
        self.assertEqual(status['anomalies'][0]['id'], 'KAK|2026-11-20')

    def test_only_documented_available_resources_resolve(self):
        for resource in ['../stations.json', 'stations/KAK/2026-11-19.json',
                         'observations/2026-11-19.json', 'stations/XXX/latest.json']:
            with self.assertRaises(KeyError):
                api.payload(resource, self.metadata, self.snapshots.__getitem__)

    def test_export_has_strict_json_and_matches_dynamic_api(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            for day, snapshot in self.snapshots.items():
                (root / 'data' / f'aggregated_{day}.json').write_text(json.dumps(snapshot))
            api.export_api(root, self.metadata)
            content = json.loads((root / 'api/v1/latest.json').read_text())
            self.assertEqual(content, api.payload('latest.json', self.metadata, self.snapshots.__getitem__))
            self.assertTrue((root / 'api/v1/stations/KAK/2026-11-20.json').exists())
        original = {'P': [float('nan'), float('inf'), 1.2]}
        self.assertEqual(api.json_safe(original), {'P': [None, None, 1.2]})
        self.assertNotEqual(original['P'][0], original['P'][0])

    def test_flask_api_is_read_only_and_cors_enabled(self):
        with patch.object(server, 'local_metadata', return_value=self.metadata), \
             patch('upload_results.build_aggregated_data', side_effect=lambda stations, day, *args: self.snapshots[day]):
            client = server.app.test_client()
            response = client.get('/api/v1/latest.json')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['Access-Control-Allow-Origin'], '*')
            self.assertEqual(response.get_json()['stations']['KAK'], self.record)
            self.assertEqual(client.post('/api/v1/latest.json').status_code, 405)
            self.assertEqual(client.get('/api/v1/private.json').status_code, 404)


if __name__ == '__main__':
    unittest.main()
