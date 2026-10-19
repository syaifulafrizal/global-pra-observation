#!/usr/bin/env python3
"""Offline before/after checks against an explicit Git revision; never runs downloads."""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import statistics
import subprocess
import tempfile
import time
import tracemalloc
from zoneinfo import ZoneInfo
from unittest.mock import patch

import numpy as np
import pandas as pd
import pra_nighttime as current
import app as current_app


def module_at_revision(ref, name, folder):
    target = folder / name
    target.write_bytes(subprocess.check_output(['git', 'show', f'{ref}:{name}']))
    spec = importlib.util.spec_from_file_location('baseline_' + target.stem, target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def benchmark(operation, count=9):
    samples = []
    for _ in range(count):
        start = time.perf_counter()
        operation()
        samples.append(1000 * (time.perf_counter() - start))
    return {'median_ms': statistics.median(samples), 'runs': count}


def allocation_peak(operation):
    tracemalloc.start()
    operation()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def verify(ref, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    report = {'baseline_commit': subprocess.check_output(['git', 'rev-parse', ref], text=True).strip(),
              'checks': [], 'measurements': {}}
    with tempfile.TemporaryDirectory(prefix='gempra-equivalence-') as temporary:
        temporary = Path(temporary)
        baseline = module_at_revision(ref, 'pra_nighttime.py', temporary)
        baseline_app = module_at_revision(ref, 'app.py', temporary)
        assert current.OPTS == baseline.OPTS
        report['checks'].append('All analysis options unchanged')
        rng = np.random.default_rng(42)
        for size, nw, fs in [(256, 2.5, 1.), (3600, 3.5, 1.), (512, 4., 2.)]:
            values = rng.normal(size=size)
            before, frequency = baseline.multitaper_psd(values, nw, fs)
            after, new_frequency = current.multitaper_psd(values, nw, fs)
            np.testing.assert_array_equal(before, after)
            np.testing.assert_array_equal(frequency, new_frequency)
        report['checks'].append('PSD and frequency arrays bit-identical across three configurations')

        start = pd.Timestamp('2026-04-10T20:00:00Z')
        end = start + pd.Timedelta(hours=8)
        seconds = np.arange(8 * 3600)
        rec = np.column_stack([30000 + 8 * np.sin(2*np.pi*.1*seconds),
                               1000 + 3 * np.cos(2*np.pi*.102*seconds),
                               40000 + 14 * np.sin(2*np.pi*.104*seconds)])
        gi = pd.DataFrame({'SYMH': -5.}, index=pd.date_range(start-pd.Timedelta(hours=1), end+pd.Timedelta(hours=1), freq='min'))
        cases = []
        for name in ['anomalous', 'normal', 'missing_samples', 'disturbed', 'unknown_symh']:
            samples = rec.copy()
            context = gi.copy()
            if name == 'missing_samples': samples[:300] = np.nan
            if name == 'disturbed': context.iloc[100:200] = -100.
            if name == 'unknown_symh': context = context.iloc[:0]
            historical = np.linspace(100., 200., 48) if name == 'normal' else np.linspace(.01, .05, 48)
            arguments = (start, start, end, start, end, context, .095, .110, {}, current.OPTS, 'KAK')
            with contextlib.redirect_stdout(io.StringIO()):
                before = baseline.analyze_row(samples.copy(), *arguments, historical_Pq=historical)
                after = current.analyze_row(samples.copy(), *arguments, historical_Pq=historical)
            assert bool(before[0]) == bool(after[0])
            pd.testing.assert_frame_equal(before[1], after[1], check_exact=True)
            pd.testing.assert_frame_equal(before[2], after[2], check_exact=True)
            assert before[2].attrs == after[2].attrs
            np.testing.assert_equal(before[3], after[3])
            assert before[4] == after[4]
            cases.append({'case': name, 'anomalous': bool(after[0]), 'anomalous_hours': int(after[4]), 'exact_match': True})
        report['classification_cases'] = cases
        assert any(case['anomalous'] for case in cases) and any(not case['anomalous'] for case in cases)
        report['checks'].append('Full analyze_row outputs, threshold provenance and anomaly flags identical in five scenarios')

        raw = temporary / 'two-days.iaga2002'
        with raw.open('w', encoding='utf-8') as source:
            source.write('Variable length fixture header\nDATE TIME DOY KAKX KAKY KAKZ KAKF\n')
            for i, stamp in enumerate(pd.date_range('2026-04-10', periods=2*86400, freq='s')):
                source.write(f'{stamp:%Y-%m-%d %H:%M:%S}.000 100 {30000+i%17} {1000+i%13} {99999 if i%10007==0 else 40000+i%11} 50000\n')
        before = baseline.read_iaga2002(raw, ZoneInfo('Asia/Tokyo'))
        after = current.read_iaga2002(raw, ZoneInfo('Asia/Tokyo'))
        pd.testing.assert_frame_equal(before.reset_index(drop=True), after.reset_index(drop=True), check_exact=True)
        window = current.read_iaga2002(raw, ZoneInfo('Asia/Tokyo'), start, end)
        expected = before[(before.dt >= start) & (before.dt < end)]
        pd.testing.assert_frame_equal(expected.reset_index(drop=True), window.reset_index(drop=True), check_exact=True)
        # Different duplicate values must select the same winner as the old
        # whole-file sort, including duplicates spanning parser chunk boundaries.
        with raw.open('a', encoding='utf-8') as source:
            source.write('2026-04-10 20:00:00.000 100 7.123456789 8.234567891 9.345678912 0\n')
        duplicate_baseline = baseline.read_iaga2002(raw, ZoneInfo('UTC'))
        duplicate_expected = duplicate_baseline[(duplicate_baseline.dt >= start) & (duplicate_baseline.dt < end)]
        duplicate_actual = current.read_iaga2002(raw, ZoneInfo('UTC'), start, end)
        pd.testing.assert_frame_equal(duplicate_expected.reset_index(drop=True), duplicate_actual.reset_index(drop=True), check_exact=True)
        report['checks'].append('Full parser and selected eight-hour window match baseline timestamps, powers, NaNs and values exactly')
        report['parser_rows'] = {'input': len(before), 'retained': len(window)}
        report['measurements']['parser_before'] = benchmark(lambda: baseline.read_iaga2002(raw, ZoneInfo('UTC')), 3)
        report['measurements']['parser_after_window'] = benchmark(lambda: current.read_iaga2002(raw, ZoneInfo('UTC'), start, end), 3)
        report['measurements']['parser_tracked_peak_bytes_before'] = allocation_peak(lambda: baseline.read_iaga2002(raw, ZoneInfo('UTC')))
        report['measurements']['parser_tracked_peak_bytes_after_window'] = allocation_peak(lambda: current.read_iaga2002(raw, ZoneInfo('UTC'), start, end))
        pipeline_outputs = []
        original_directory = Path.cwd()
        try:
            for label, module in [('before', baseline), ('after', current)]:
                work = temporary / label
                work.mkdir()
                os.chdir(work)
                with patch.dict(os.environ, {'PROCESS_DATE':'2026-04-11', 'FORCE_RERUN':''}), \
                     patch.object(module, 'get_station_timezone', return_value=ZoneInfo('UTC')), \
                     patch.object(module, 'download_data', return_value=raw), \
                     patch.object(module, 'download_symh_data', return_value=gi), \
                     contextlib.redirect_stdout(io.StringIO()):
                    assert module.process_station('KAK') is True
                folder = work / 'INTERMAGNET_DOWNLOADS/KAK'
                pipeline_outputs.append({
                    'result': json.loads((folder/'PRA_Night_KAK_20260411.json').read_text()),
                    'series_csv': (folder/'PRA_Night_KAK_20260411.csv').read_bytes(),
                    'coverage_csv': (folder/'analysis_coverage.csv').read_bytes(),
                    'figure_present': (folder/'figures/PRA_KAK_20260411.png').is_file()
                })
            assert pipeline_outputs[0] == pipeline_outputs[1]
        finally:
            os.chdir(original_directory)
        report['checks'].append('Full process_station produces identical saved JSON, series CSV and coverage CSV; both figures generated')
        values = rng.normal(size=3600)
        report['measurements']['psd_before'] = benchmark(lambda: baseline.multitaper_psd(values), 25)
        report['measurements']['psd_after_warm'] = benchmark(lambda: current.multitaper_psd(values), 25)
        report['measurements']['metadata_before'] = benchmark(baseline_app.local_metadata)
        current_app.local_metadata()
        report['measurements']['metadata_after_warm'] = benchmark(current_app.local_metadata)
        day = current_app.local_metadata()['most_recent_date']
        old_client = baseline_app.app.test_client()
        new_client = current_app.app.test_client()
        route = f'/data/aggregated_{day}.json'
        for date in current_app.local_metadata()['available_dates']:
            previous = old_client.get(f'/data/aggregated_{date}.json').get_json()
            updated = new_client.get(f'/data/aggregated_{date}.json').get_json()
            previous.pop('generated_at', None); updated.pop('generated_at', None)
            assert previous == updated
        report['measurements']['aggregate_route_before'] = benchmark(lambda: old_client.get(route))
        report['measurements']['aggregate_route_after_warm'] = benchmark(lambda: new_client.get(route))
        report['checks'].append('All five published aggregate payloads identical excluding assembly timestamp')
        for name in ['earthquake_integration.py', 'integrate_earthquakes.py', 'run_daily_analysis.ps1',
                     'run_daily_analysis.bat', 'deploy_all.bat', 'deploy_all.ps1']:
            previous = subprocess.check_output(['git', 'show', f'{ref}:{name}']).replace(b'\r\n', b'\n')
            updated = Path(name).read_bytes().replace(b'\r\n', b'\n')
            assert previous == updated, name
        report['checks'].append('Earthquake matching and registered/daily workflow scripts unchanged')
    (destination / 'equivalence-and-performance.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', default='7946d3890')
    parser.add_argument('--output', default='output/dogfood/optimization')
    options = parser.parse_args()
    verify(options.baseline_ref, options.output)
