"""Offline regression checks. All writes are confined to temporary directories."""

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import subprocess
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
import pra_nighttime as pra
import download_symh as symh
import earthquake_integration as earthquakes
import upload_results as output
import app as server
from result_validation import result_is_usable


def sample_result(date, **extra):
    result = {'station': 'KAK', 'date': date, 'P': [1., 1.2],
              'nZ': [4., 5.], 'nG': [4., 4.2], 'isQuiet': [True, True],
              'isAnomalous': [False, False], 'is_anomalous': False,
              'nAnomHours': 0, 'threshold': 2.}
    result.update(extra)
    return result


class LocalFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='gempra-regression-')
        self.directory = Path(self.temporary.name)
        self.previous = Path.cwd()
        os.chdir(self.directory)
        self.environment = patch.dict(os.environ, {'PROCESS_DATE': '2026-04-11',
                                                  'INTERMAGNET_STATIONS': 'KAK', 'FORCE_RERUN': ''})
        self.environment.start()
        Path('stations.json').write_text(json.dumps({'stations': [{
            'code': 'KAK', 'timezone': 'UTC', 'latitude': 36., 'longitude': 140.,
            'name': 'Test station', 'country': 'Test'}]}))
        self.station = Path('INTERMAGNET_DOWNLOADS/KAK')
        self.station.mkdir(parents=True)
        self.quiet_print = contextlib.redirect_stdout(io.StringIO())
        self.quiet_print.__enter__()

    def tearDown(self):
        self.quiet_print.__exit__(None, None, None)
        self.environment.stop()
        os.chdir(self.previous)
        self.temporary.cleanup()

    def result(self, date, **extra):
        result = sample_result(date, **extra)
        path = self.station / f'PRA_Night_KAK_{date.replace("-", "")}.json'
        path.write_text(json.dumps(result))
        return path

    def anomaly(self, date=None):
        detection = pd.Timestamp(date or '2026-04-11T04:00:00')
        begin = detection - timedelta(days=1)
        pd.DataFrame([{'Range': f'{begin:%d/%m/%Y} 20:00 - {detection:%d/%m/%Y} 04:00',
                       'DetectionTimeUTC': detection.isoformat(), 'Times': '21:00'}]).to_csv(
                           self.station / 'anomaly_master_table.csv', index=False)
        return detection

    def event(self, when):
        frame = pd.DataFrame([{'time': pd.Timestamp(when), 'magnitude': 5.5,
                               'latitude': 36., 'longitude': 140., 'place': 'Offline, fixture', 'id': 'test'}])
        frame.attrs['query_succeeded'] = True
        return frame

    def test_parser_preserves_gaps_and_masks_fill_values(self):
        path = Path('variable-header.iaga2002')
        path.write_text('header\nDATE TIME DOY KAKX KAKY KAKZ KAKF\n'
                        '2026-04-10 20:00:00.000 100 99999 99999 99999 99999\n'
                        '2026-04-10 20:00:02.000 100 3 4 5 6\n')
        data = pra.read_iaga2002(path, ZoneInfo('UTC'))
        self.assertEqual(len(data), 2)
        self.assertTrue(data[['X', 'Y', 'Z']].iloc[0].isna().all())
        self.assertEqual((data.dt.iloc[1] - data.dt.iloc[0]).total_seconds(), 2)

    def test_rejected_html_is_not_cached_as_iaga(self):
        response = Mock(text='<html>Request Rejected</html>', content=b'rejected')
        with patch.object(pra.requests, 'get', return_value=response):
            self.assertIsNone(pra.download_data('KAK', datetime(2026, 4, 10), self.station))
        self.assertFalse(list(self.station.glob('*.iaga2002')))

    def test_native_non_xyz_is_not_silently_misread(self):
        path = Path('hdz.iaga2002')
        path.write_text('DATE TIME DOY KAKH KAKD KAKZ\n2026-04-10 20:00:00 100 3 4 5\n')
        self.assertTrue(pra.read_iaga2002(path, ZoneInfo('UTC')).empty)

    def test_legacy_constant_fill_spectra_are_not_usable(self):
        data = sample_result('2026-04-11', P=[.5, .5], nZ=[20., 20.], nG=[40., 40.])
        self.assertFalse(result_is_usable(data))
        self.assertTrue(result_is_usable(sample_result('2026-04-11')))

    def test_missing_symh_is_unknown(self):
        quiet, fractions = pra.compute_quiet_flags(pd.Series(pd.to_datetime(['2026-04-10T20:30:00Z'])),
                                                   symh.empty_symh(), .05, False, .02, -30)
        self.assertFalse(quiet.any())
        self.assertTrue(np.isnan(fractions).all())

    def test_naive_disturbed_symh_and_sparse_coverage(self):
        times = pd.Series(pd.to_datetime(['2026-04-10T20:30:00Z']))
        data = pd.DataFrame({'SYMH': -100.}, index=pd.date_range('2026-04-10T20:00', periods=61, freq='min'))
        quiet, fractions = pra.compute_quiet_flags(times, data, .05, False, .02, -30)
        self.assertFalse(quiet.any())
        self.assertEqual(fractions[0], 1.)
        quiet, fractions = pra.compute_quiet_flags(times, data.iloc[:2], .05, False, .02, -30)
        self.assertFalse(quiet.any())
        self.assertTrue(np.isnan(fractions[0]))

    def test_minute_symh_parser_and_recent_request(self):
        text = '<pre>\nYEAR DOY HR MN SYM/H\n2026 100 20 00 -42\n2026 100 20 01 99999\n2026 100 20 02 7\n</pre>'
        response = Mock(text=text)
        with patch.object(symh.requests, 'get', return_value=response) as request:
            result = symh.download_symh_omniweb(datetime(2026, 4, 10), datetime(2026, 4, 11), Path('cache.csv'))
        self.assertEqual(result.SYMH.tolist(), [-42., 7.])
        self.assertEqual(str(result.index.tz), 'UTC')
        self.assertEqual(request.call_args.kwargs['params']['vars'], '41')
        self.assertEqual(request.call_args.kwargs['params']['spacecraft'], 'omni_min')
        self.assertEqual(request.call_args.kwargs['params']['start_date'], '20260410')

    def test_evt_fit_and_small_sample_fallback(self):
        values = np.random.default_rng(123).exponential(size=160)
        value, method = pra.fit_evt_threshold(values, .75, .05, 0, 4, return_details=True)
        self.assertEqual(method, 'evt')
        self.assertGreater(value, np.quantile(values, .75))
        value, method = pra.fit_evt_threshold(values[:56], .75, .05, 0, 4, return_details=True)
        self.assertEqual(method, 'k_sigma')
        self.assertAlmostEqual(value, np.mean(values[:56]) + 4 * np.std(values[:56]))

    def test_evt_false_positive_target_is_for_whole_distribution(self):
        values = np.arange(160.)
        with patch.object(pra.genpareto, 'fit', return_value=(0., 0., 2.)):
            value = pra.fit_evt_threshold(values, .75, .05, 0, 4)
        expected = np.quantile(values, .75) - 2 * np.log(.05 / .25)
        self.assertAlmostEqual(value, expected)

    def test_current_outlier_does_not_raise_historical_threshold(self):
        times = pd.Series(pd.date_range('2026-04-10T20:30Z', periods=2, freq='h'))
        series = (np.array([100., 110.]), np.array([10., 10.]), np.ones(2), times,
                  np.ones(2, dtype=bool), np.zeros(2))
        history = np.arange(1., 25.)
        with patch.object(pra, 'compute_pseries', return_value=series):
            result = pra.analyze_row(None, None, None, pd.Timestamp('2026-04-11T00:00Z'),
                None, None, None, .095, .110, {}, pra.OPTS, 'KAK', history)
        self.assertAlmostEqual(result[3], history.mean() + 4 * history.std())
        self.assertEqual(result[2].attrs['baseline_source'], 'historical')

    def test_forward_event_matches_and_earlier_event_does_not(self):
        self.anomaly()
        events = pd.concat([self.event('2026-04-08T12:00'), self.event('2026-04-12T12:00')], ignore_index=True)
        with patch.object(earthquakes, 'fetch_usgs_earthquakes', return_value=events):
            result = earthquakes.correlate_anomalies_with_earthquakes('KAK', self.station)
        self.assertEqual(result.iloc[0]['status'], 'TP')
        self.assertEqual(str(result.iloc[0]['anomaly_date'].date()), '2026-04-11')
        self.assertGreater(result.iloc[0]['days_after_anomaly'], 0)
        self.assertEqual(result.iloc[0]['earthquake_time'], pd.Timestamp('2026-04-12T12:00'))

    def test_pending_and_failed_queries_never_become_false_positives(self):
        self.anomaly(pd.Timestamp.utcnow().tz_localize(None) - timedelta(days=1))
        with patch.object(earthquakes, 'fetch_usgs_earthquakes', return_value=earthquakes.empty_earthquakes(True)):
            result = earthquakes.correlate_anomalies_with_earthquakes('KAK', self.station)
            self.assertEqual(result.iloc[0]['status'], 'Pending')
        with patch.object(earthquakes, 'fetch_usgs_earthquakes', return_value=earthquakes.empty_earthquakes(False)):
            result = earthquakes.correlate_anomalies_with_earthquakes('KAK', self.station)
            self.assertEqual(result.iloc[0]['status'], 'Unknown')

    def test_blank_magnitude_does_not_confirm_correlation(self):
        for status in ['Pending', 'FP', 'Unknown', 'TP']:
            pd.DataFrame([{'anomaly_date': '2026-04-11', 'status': status,
                           'earthquake_magnitude': None}]).to_csv(self.station / 'earthquake_correlations.csv', index=False)
            self.assertFalse(output.station_has_correlation(self.station, '2026-04-11'))
        for value in ('NaN', 'inf', '-inf'):
            self.assertIsNone(output.safe_float(value))

    def test_false_negatives_require_observed_forecast_window(self):
        when = pd.Timestamp.utcnow().tz_localize(None).normalize() - timedelta(hours=12)
        days = [str((when - timedelta(days=i)).date()) for i in range(14)]
        pd.DataFrame({'date': days, 'complete': [False] * 14}).to_csv(self.station / 'analysis_coverage.csv', index=False)
        with patch.object(earthquakes, 'fetch_usgs_earthquakes', return_value=self.event(when)):
            self.assertTrue(earthquakes.find_false_negatives('KAK', self.station).empty)
        pd.DataFrame({'date': days, 'complete': [True] * 14}).to_csv(self.station / 'analysis_coverage.csv', index=False)
        with patch.object(earthquakes, 'fetch_usgs_earthquakes', return_value=self.event(when)):
            result = earthquakes.find_false_negatives('KAK', self.station)
            self.assertEqual(len(result), 1)
            self.assertTrue(result.iloc[0]['coverage_verified'])

    def test_archive_history_survives_stale_web_snapshot(self):
        archive = Path('data/history/false_negative_history.json')
        archive.parent.mkdir(parents=True)
        archive.write_text(json.dumps({'entries': [{'station': 'KAK', 'earthquake_time': '2026-04-01'}]}))
        web = Path('web_output/data'); web.mkdir(parents=True)
        (web / 'false_negative_history.json').write_text('{"entries": []}')
        entries = output.update_false_negative_history(['KAK'], web)
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(json.loads(archive.read_text())['entries']), 1)

    def test_aggregate_keeps_actual_dates_and_invalid_data_out(self):
        self.result('2026-04-10')
        aggregate = output.build_aggregated_data(['KAK'], '2026-04-11', Path('unused'), Path('INTERMAGNET_DOWNLOADS'))
        self.assertEqual(aggregate['station_dates']['KAK'], '2026-04-10')
        self.assertTrue(aggregate['is_hybrid_aggregation'])
        self.result('2026-04-11', P=[.5, .5], nZ=[20., 20.], nG=[40., 40.])
        aggregate = output.build_aggregated_data(['KAK'], '2026-04-11', Path('unused'), Path('INTERMAGNET_DOWNLOADS'))
        self.assertNotIn('KAK', aggregate['stations'])
        self.assertEqual(aggregate['station_quality']['KAK'], 'invalid')

    def test_preparation_does_not_alias_adjacent_nights_or_consume_inputs(self):
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        self.result(today.isoformat())
        self.result(yesterday.isoformat())
        Path('static').mkdir(); Path('templates').mkdir()
        Path('static/assets').mkdir()
        Path('static/assets/emblem.png').write_bytes(b'fixture asset')
        Path('templates/index.html').write_text('<html>fixture</html>')
        input_csv = Path(f'recent_earthquakes_{today}.csv'); input_csv.write_text('id\nfixture\n')
        output.prepare_web_output()
        for date in [today, yesterday]:
            result = json.loads(Path(f'web_output/data/KAK_{date}.json').read_text())
            self.assertEqual(result['date'], date.isoformat())
        self.assertTrue(input_csv.exists())
        self.assertEqual(Path('web_output/static/assets/emblem.png').read_bytes(), b'fixture asset')

    def test_daily_export_advertises_only_dates_with_actual_usable_results(self):
        from validate_pages_output import validate_pages_output
        day = '2026-04-11'
        self.result(day)
        self.result('2026-04-12', P=[.5,.5], nZ=[20.,20.], nG=[40.,40.])
        Path('templates').mkdir(); Path('static').mkdir()
        Path('templates/index.html').write_text('<html>fixture</html>')
        Path('static/app.js').write_text('// fixture')
        Path('static/style.css').write_text('/* fixture */')
        output.prepare_web_output()
        metadata = json.loads(Path('web_output/data/stations.json').read_text())
        self.assertEqual(metadata['available_dates'], [day])
        self.assertEqual(metadata['most_recent_date'], day)
        self.assertTrue(Path(f'web_output/data/aggregated_{day}.json').is_file())
        self.assertEqual(validate_pages_output('web_output')['latest'],day)

    def test_publication_gate_rejects_phantom_dates_and_fallback_only_nights(self):
        from validate_pages_output import validate_pages_output
        web = Path('web_output'); (web/'data').mkdir(parents=True); (web/'static').mkdir()
        for name in ['index.html','static/app.js','static/style.css']:
            (web/name).write_text('fixture')
        metadata={'stations':['KAK'],'available_dates':['2026-04-12'],'most_recent_date':'2026-04-12'}
        (web/'data/stations.json').write_text(json.dumps(metadata))
        with self.assertRaisesRegex(ValueError,'no aggregate'):
            validate_pages_output(web)
        (web/'data/aggregated_2026-04-12.json').write_text(json.dumps({'stations':{'KAK':sample_result('2026-04-11')}}))
        with self.assertRaisesRegex(ValueError,'no usable observations for that night'):
            validate_pages_output(web)

    def test_export_without_results_preserves_existing_output(self):
        web=Path('web_output');web.mkdir();existing=web/'index.html';existing.write_text('previous working site')
        with self.assertRaisesRegex(ValueError,'No usable station-night results'):
            output.prepare_web_output()
        self.assertEqual(existing.read_text(),'previous working site')

    @unittest.skipUnless(os.name == 'nt', 'Windows deployment gate')
    def test_daily_deployment_stops_before_git_when_default_date_has_no_results(self):
        import shutil
        for name in ('deploy_to_github.ps1','validate_pages_output.py','result_validation.py'):
            shutil.copy2(ROOT/name, Path(name))
        web=Path('web_output');(web/'static').mkdir(parents=True);(web/'data').mkdir()
        for name in ('index.html','static/app.js','static/style.css'):
            (web/name).write_text('fixture')
        (web/'data/stations.json').write_text(json.dumps({'stations':['KAK'],
            'available_dates':['2026-10-20'],'most_recent_date':'2026-10-20'}))
        completed=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
            '-File',str(Path('deploy_to_github.ps1').resolve())],capture_output=True,text=True,errors='replace',timeout=30)
        self.assertNotEqual(completed.returncode,0)
        self.assertIn('Publication blocked',completed.stdout+completed.stderr)
        self.assertFalse(Path('.git').exists())

    def test_static_preview_matches_local_snapshots_and_refuses_overwrites(self):
        from build_pages_preview import build_preview
        source = self.result('2026-04-11')
        original = source.read_bytes()
        Path('templates').mkdir()
        Path('templates/index.html').write_bytes((ROOT / 'templates/index.html').read_bytes())
        Path('static/assets').mkdir(parents=True)
        for name in ('app.js', 'style.css'):
            Path('static', name).write_bytes((ROOT / 'static' / name).read_bytes())
        for name in ('gempra-field-emblem.png', 'gempra-emblem-96.png', 'gempra-favicon-32.png'):
            Path('static/assets', name).write_bytes(b'fixture asset')
        destination = Path('unpublished')
        manifest = build_preview(destination)
        self.assertEqual(manifest['publication_status'], 'unpublished_preview')
        self.assertEqual(json.loads((destination / 'data/stations.json').read_text())['most_recent_date'], '2026-04-11')
        self.assertEqual((destination / 'static/assets/gempra-field-emblem.png').read_bytes(), b'fixture asset')
        self.assertEqual(source.read_bytes(), original)
        self.assertTrue((destination / '.nojekyll').exists())
        with self.assertRaises(FileExistsError):
            build_preview(destination)

    def test_flask_uses_current_metadata_and_matching_source_assets(self):
        self.result('2026-04-11')
        web = Path('web_output/data'); web.mkdir(parents=True)
        (web / 'stations.json').write_text('{"most_recent_date": "2025-12-23"}')
        (web / 'KAK_2026-04-11.json').write_text('{"date": "2026-04-12"}')
        with server.app.test_client() as client:
            metadata = client.get('/data/stations.json').get_json()
            self.assertEqual(metadata['most_recent_date'], '2026-04-11')
            with client.get('/static/app.js') as response:
                self.assertEqual(response.data, (ROOT / 'static/app.js').read_bytes())
            self.assertIn(b'Matched Anomaly Rate', client.get('/').data)
            self.assertEqual(client.get('/api/stations').get_json(), ['KAK'])
            self.assertEqual(client.get('/data/KAK_2026-04-11.json').get_json()['date'], '2026-04-11')

    def test_backfill_calls_seven_distinct_dates_without_forcing_overwrites(self):
        import initialize_7day_dataset as initializer
        with patch.object(initializer, 'load_stations', return_value=[{'code': 'KAK'}]), \
             patch.object(initializer, 'get_station_timezone', return_value=ZoneInfo('UTC')), \
             patch.object(initializer, 'download_data', return_value=None), \
             patch.object(initializer, 'process_station_for_date', return_value=True) as process, \
             patch('subprocess.run', return_value=Mock(returncode=0)):
            self.assertEqual(initializer.main(), 0)
        days = [call.args[1] for call in process.call_args_list]
        self.assertEqual(len(set(days)), 7)
        self.assertEqual(days, sorted(days))
        self.assertEqual(os.environ['FORCE_RERUN'], '')

    def test_existing_results_are_never_automatically_overwritten(self):
        path = self.result('2026-04-11')
        before = path.read_bytes()
        with patch.object(pra, 'get_station_timezone', return_value=ZoneInfo('UTC')):
            self.assertTrue(pra.process_station('KAK'))
        self.assertEqual(path.read_bytes(), before)

    def test_synthetic_eight_hour_night_runs_through_existing_pipeline(self):
        start = pd.Timestamp('2026-04-10T20:00Z')
        times = pd.date_range(start, periods=8 * 3600, freq='s')
        seconds = np.arange(len(times))
        values = pd.DataFrame({'DATE': times.strftime('%Y-%m-%d'), 'TIME': times.strftime('%H:%M:%S.000'),
            'DOY': 100, 'KAKX': 30000 + 4 * np.sin(2 * np.pi * .1 * seconds),
            'KAKY': 4000 + np.sin(2 * np.pi * .101 * seconds),
            'KAKZ': 40000 + 2 * np.sin(2 * np.pi * .1 * seconds), 'KAKF': 50000})
        raw = Path('synthetic.iaga2002')
        values.to_csv(raw, sep=' ', index=False)
        context = pd.DataFrame({'SYMH': 0.}, index=pd.date_range(start - timedelta(hours=1), periods=601, freq='min'))
        with patch.object(pra, 'get_station_timezone', return_value=ZoneInfo('UTC')), \
             patch.object(pra, 'download_data', return_value=raw), \
             patch.object(pra, 'download_symh_data', return_value=context):
            self.assertTrue(pra.process_station('KAK'))
        result = json.loads((self.station / 'PRA_Night_KAK_20260411.json').read_text())
        self.assertEqual(len(result['P']), 8)
        self.assertEqual(result['data_quality']['status'], 'complete')
        self.assertTrue(result['data_quality']['symh_verified'])
        self.assertEqual(result['threshold_method'], 'k_sigma')
        self.assertEqual(result['baseline_source'], 'warmup')
        self.assertTrue((self.station / 'figures/PRA_KAK_20260411.png').exists())
        self.assertTrue((self.station / 'analysis_coverage.csv').exists())

    def test_station_failure_returns_nonzero_workflow_status(self):
        with patch.object(pra, 'process_station', return_value=False):
            self.assertEqual(pra.main(), 1)

    def test_flask_cache_revalidates_results_metadata_and_correlation_files(self):
        path = self.result('2026-04-11')
        client = server.app.test_client()
        route = '/data/aggregated_2026-04-11.json'
        first = client.get(route).get_json()
        repeated = client.get(route).get_json()
        self.assertEqual(first, repeated)
        changed = json.loads(path.read_text())
        changed['P'][0] = 1.5
        path.write_text(json.dumps(changed))
        self.assertEqual(client.get(route).get_json()['stations']['KAK']['P'][0], 1.5)
        pd.DataFrame([{'anomaly_date':'2026-04-11', 'status':'TP', 'earthquake_magnitude':5.5,
                       'earthquake_distance_km':100, 'days_after_anomaly':2,
                       'detection_time_utc':'2026-04-11T04:00:00Z',
                       'earthquake_time':'2026-04-13T04:00:00Z'}]).to_csv(
            self.station / 'earthquake_correlations.csv', index=False)
        self.assertEqual(client.get(route).get_json()['earthquake_correlations']['KAK'][0]['status'], 'TP')
        self.result('2026-04-12')
        self.assertEqual(client.get('/data/stations.json').get_json()['most_recent_date'], '2026-04-12')
        path.unlink()
        self.assertNotIn('KAK', client.get(route).get_json()['stations'])


if __name__ == '__main__':
    unittest.main()
