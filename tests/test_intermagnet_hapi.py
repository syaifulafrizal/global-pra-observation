"""Official HAPI transport: offline binary fixtures, metadata and atomic-file guards."""
import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

import intermagnet_hapi as hapi
import pra_nighttime as pra


def metadata(**changes):
    info = {'status': {'code': 1200}, 'cadence': 'PT1S',
            'startDate': '2000-01-01T00:00:00Z', 'stopDate': '2030-01-01T00:00:00Z', 'parameters': [
        {'name': 'Time', 'type': 'isotime', 'length': 20, 'units': 'UTC'},
        {'name': 'Field_Vector', 'type': 'double', 'size': [3], 'units': ['nT'] * 3,
         'coordinateSystemName': 'Cartesian', 'vectorComponents': ['x', 'y', 'z'], 'fill': '99999.0'},
    ]}
    info.update(changes)
    return info


def product():
    return hapi.Product(99999., datetime(2000, 1, 1, tzinfo=timezone.utc), datetime(2030, 1, 1, tzinfo=timezone.utc))


class HapiTransport(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='gempra-hapi-')
        self.path = Path(self.folder.name) / 'KAK_20260410.iaga2002'
        self.start = datetime(2026, 4, 10, tzinfo=timezone.utc)
        hapi._metadata.cache_clear()
        self.real_availability = hapi._has_adjusted_samples
        self.availability = patch.object(hapi, '_has_adjusted_samples', return_value=True)
        self.availability.start()

    def tearDown(self):
        self.folder.cleanup()
        self.availability.stop()
        hapi._metadata.cache_clear()

    def record(self, stamp, values=(1.235, -2.675, 99999.0)):
        return hapi.RECORD.pack(stamp.strftime('%Y-%m-%dT%H:%M:%SZ').encode('ascii'), *values)

    def test_four_exclusive_utc_intervals_preserve_precision_and_gaps(self):
        calls = []
        def request(endpoint, params, limit):
            calls.append((endpoint, params))
            if endpoint == 'info':
                return json.dumps(metadata()).encode()
            stamp = datetime.fromisoformat(params['time.min'].replace('Z', '+00:00'))
            # Keep a real missing timestamp; no interpolation or time compression.
            return self.record(stamp) + self.record(stamp + timedelta(seconds=2))
        with patch.object(hapi, '_request', side_effect=request), contextlib.redirect_stdout(io.StringIO()):
            result = hapi.download_iaga('KAK', self.start, self.path)
        self.assertEqual(result, self.path)
        self.assertFalse(self.path.with_suffix('.iaga2002.tmp').exists())
        frame = pra.read_iaga2002(self.path, timezone.utc)
        self.assertEqual(len(frame), 8)
        self.assertEqual(frame.X.tolist(), [1.24] * 8)
        self.assertEqual(frame.Y.tolist(), [-2.68] * 8)
        self.assertTrue(frame.Z.isna().all())
        self.assertEqual((frame.dt.iloc[1] - frame.dt.iloc[0]).total_seconds(), 2)
        requests = [params for endpoint, params in calls if endpoint == 'data']
        self.assertEqual(len(requests), 4)
        self.assertEqual(requests[0]['time.min'], '2026-04-10T00:00:00Z')
        self.assertEqual(requests[-1]['time.max'], '2026-04-11T00:00:00Z')
        self.assertTrue(all(params['id'] == 'kak/adjusted/PT1S/xyzf' and params['format'] == 'binary'
                            and params['parameters'] == 'Time,Field_Vector' for params in requests))

    def test_wrong_cadence_units_or_coordinates_are_rejected(self):
        cases = []
        for change in ({'cadence': 'PT1M'}, {'status': {'code': 1406}}):
            cases.append(metadata(**change))
        for field, value in [('units', ['degrees'] * 3), ('vectorComponents', ['h', 'd', 'z']),
                             ('size', [4]), ('type', 'integer'), ('coordinateSystemName', 'Spherical')]:
            info = metadata(); info['parameters'][1][field] = value; cases.append(info)
        for info in cases:
            with self.subTest(info=info), patch.object(hapi, '_request', return_value=json.dumps(info).encode()):
                hapi._metadata.cache_clear()
                with self.assertRaises(hapi.HapiUnavailable):
                    hapi.download_iaga('KAK', self.start, self.path)
                self.assertFalse(self.path.exists())

    def test_truncated_duplicate_and_out_of_interval_records_preserve_existing_file(self):
        self.path.write_bytes(b'original data')
        for body in (self.record(self.start)[:-1], self.record(self.start) * 2,
                     self.record(self.start + timedelta(hours=6)),
                     self.record(self.start - timedelta(seconds=1)), b'not a binary observation'):
            with self.subTest(body=body[:25]), patch.object(hapi, '_metadata', return_value=product()), \
                 patch.object(hapi, '_request', return_value=body):
                with self.assertRaises(hapi.HapiUnavailable):
                    hapi.download_iaga('KAK', self.start, self.path)
                self.assertEqual(self.path.read_bytes(), b'original data')
                self.assertFalse(self.path.with_suffix('.iaga2002.tmp').exists())

    def test_explicit_no_data_is_not_cached_as_a_measurement(self):
        for body in (b'', b'{"status":{"code":1201,"message":"No data"}}'):
            with self.subTest(body=body), patch.object(hapi, '_metadata', return_value=product()), \
                 patch.object(hapi, '_request', return_value=body):
                with self.assertRaises(hapi.NoAdjustedData):
                    hapi.download_iaga('KAK', self.start, self.path)
                self.assertFalse(self.path.exists())
                self.assertFalse(self.path.with_suffix('.iaga2002.tmp').exists())

    def test_partial_network_transfer_retries_without_returning_partial_bytes(self):
        first = Mock(headers={})
        def broken_chunks(size):
            yield b'partial'
            raise hapi.requests.exceptions.ChunkedEncodingError('reset')
        first.iter_content.side_effect = broken_chunks
        second = Mock(headers={'Content-Length': '8'})
        second.iter_content.return_value = [b'complete']
        with patch.object(hapi.requests, 'get', side_effect=[first, second]) as get, \
             patch.object(hapi.time, 'sleep') as sleep, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(hapi._request('data', {'id': 'kak/adjusted/PT1S/xyzf'}, 100), b'complete')
        self.assertEqual(get.call_count, 2)
        sleep.assert_called_once_with(1)
        first.close.assert_called_once(); second.close.assert_called_once()

    def test_transfer_time_size_and_content_length_limits_are_enforced(self):
        for headers, chunks, clock in (({}, [b'x' * 101], [0., 1.]),
                                        ({'Content-Length': '5'}, [b'abc'], [0., 1.]),
                                        ({}, [b'abc'], [0., 46.])):
            with self.subTest(headers=headers, clock=clock):
                responses = []
                for _ in range(3):
                    response = Mock(headers=headers); response.iter_content.return_value = chunks; responses.append(response)
                with patch.object(hapi.requests, 'get', side_effect=responses), \
                     patch.object(hapi.time, 'monotonic', side_effect=clock * 3), \
                     patch.object(hapi.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(hapi.HapiUnavailable):
                        hapi._request('data', {'id': 'test'}, 100)
                self.assertTrue(responses[0].close.called)

    def test_cache_and_legacy_fallback_remain_supported(self):
        self.path.write_text('DATE TIME DOY KAKX KAKY KAKZ\n2026-04-10 00:00:00 100 1 2 3\n')
        with patch.object(pra, 'download_hapi') as download:
            self.assertEqual(pra.download_data('KAK', self.start, self.path.parent), self.path)
        download.assert_not_called()
        with tempfile.TemporaryDirectory(prefix='gempra-hapi-fallback-') as tmp:
            def legacy(station, day, path):
                path.write_bytes(self.path.read_bytes())
                return path
            with patch.dict('os.environ', {'INTERMAGNET_TRANSPORT': 'auto'}), \
                 patch.object(pra, 'download_hapi', side_effect=hapi.HapiUnavailable('unsupported product')), \
                 patch.object(pra, 'download_legacy', side_effect=legacy), contextlib.redirect_stdout(io.StringIO()):
                result = pra.download_data('KAK', self.start, Path(tmp))
            self.assertEqual(result.read_bytes(), self.path.read_bytes())

    def test_no_data_day_does_not_fabricate_a_normal_classification(self):
        with patch.dict('os.environ', {'INTERMAGNET_TRANSPORT': 'auto'}), \
             patch.object(pra, 'download_hapi', side_effect=hapi.NoAdjustedData('No data')), \
             patch.object(pra.requests, 'get') as request, contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(pra.download_data('KAK', self.start, self.path.parent))
        request.assert_not_called()
        self.assertIn(('KAK', '2026-04-10'), pra._no_adjusted_data)
        self.assertFalse(self.path.exists())
        pra._no_adjusted_data.clear()

    def test_directory_zero_skips_embargoed_data_without_downloading_fake_samples(self):
        with patch.object(hapi, '_has_adjusted_samples', return_value=False), \
             patch.object(hapi, '_metadata') as info, patch.object(hapi, '_request') as request:
            with self.assertRaises(hapi.NoAdjustedData):
                hapi.download_iaga('KAK', self.start, self.path)
        info.assert_not_called(); request.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_directory_requires_the_exact_station_date_and_publication_state(self):
        row = {'date': '10-04-2026', 'samples_recorded': 0, 'samples_missing': 86400}
        valid = {'data': [{'iaga_code': 'KAK', 'publication_state': 'adjusted', 'days': [row]}]}
        with patch.object(hapi, '_request', return_value=json.dumps(valid).encode()):
            self.assertFalse(self.real_availability('KAK', self.start))
        for key, value in [('iaga_code', 'HER'), ('publication_state', 'reported')]:
            data = json.loads(json.dumps(valid)); data['data'][0][key] = value
            with self.subTest(key=key), patch.object(hapi, '_request', return_value=json.dumps(data).encode()):
                with self.assertRaises(hapi.HapiUnavailable):
                    self.real_availability('KAK', self.start)
        for value in (False, -1, 86401, '0'):
            data = json.loads(json.dumps(valid)); data['data'][0]['days'][0]['samples_recorded'] = value
            with self.subTest(value=value), patch.object(hapi, '_request', return_value=json.dumps(data).encode()):
                with self.assertRaises(hapi.HapiUnavailable):
                    self.real_availability('KAK', self.start)

    def test_failed_directory_does_not_hide_available_hapi_data(self):
        def request(endpoint, params, limit):
            stamp = datetime.fromisoformat(params['time.min'].replace('Z', '+00:00'))
            return self.record(stamp, (1., 2., 3.))
        with patch.object(hapi, '_has_adjusted_samples', side_effect=hapi.HapiUnavailable('directory offline')), \
             patch.object(hapi, '_metadata', return_value=product()), patch.object(hapi, '_request', side_effect=request), \
             contextlib.redirect_stdout(io.StringIO()):
            hapi.download_iaga('KAK', self.start, self.path)
        self.assertEqual(len(pra.read_iaga2002(self.path, timezone.utc)), 4)

    def test_bounded_legacy_fallback_preserves_received_iaga_bytes(self):
        body = b'DATE TIME DOY KAKX KAKY KAKZ\n2026-04-10 00:00:00 100 1 2 3\n'
        with patch.object(hapi, '_request', return_value=body) as request:
            hapi.download_legacy('KAK', self.start, self.path)
        self.assertEqual(self.path.read_bytes(), body)
        self.assertEqual(request.call_args.args[1]['publicationState'], 'adjusted')
        self.assertEqual(request.call_args.args[1]['samplesPerDay'], 'second')
        self.assertEqual(request.call_args.args[1]['orientation'], 'XYZF')
        with patch.object(hapi, '_request', return_value=b'<html>Unavailable</html>'):
            with self.assertRaises(hapi.HapiUnavailable):
                hapi.download_legacy('KAK', self.start, self.path)
        self.assertEqual(self.path.read_bytes(), body)

    def test_partial_day_requests_respect_the_published_hapi_time_bounds(self):
        available = hapi.Product(99999., self.start + timedelta(minutes=5), self.start + timedelta(hours=3, minutes=3, seconds=4))
        calls = []
        def request(endpoint, params, limit):
            calls.append(params)
            return self.record(self.start + timedelta(minutes=5))
        with patch.object(hapi, '_metadata', return_value=available), patch.object(hapi, '_request', side_effect=request), \
             contextlib.redirect_stdout(io.StringIO()):
            hapi.download_iaga('KAK', self.start, self.path)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['time.min'], '2026-04-10T00:05:00Z')
        self.assertEqual(calls[0]['time.max'], '2026-04-10T03:03:04Z')
