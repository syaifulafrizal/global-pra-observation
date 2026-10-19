"""Correctness guards for bounded caches and selective parsing (offline fixtures)."""
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.signal import windows

import pra_nighttime as pra
from snapshot_cache import SnapshotCache, file_revisions


class PerformanceSafety(unittest.TestCase):
    def test_cached_spectra_equal_original_fft_accumulation(self):
        rng = np.random.default_rng(7)
        for size, nw, fs in [(256, 2.5, 1.), (3600, 3.5, 1.), (512, 4., 2.)]:
            signal = rng.normal(size=size)
            tapers, weights = windows.dpss(size, nw, int(2 * nw - 1), return_ratios=True)
            expected = np.zeros(size)
            for taper, weight in zip(tapers, weights):
                expected += np.abs(np.fft.fft(signal * taper)) ** 2 * weight
            expected /= len(weights)
            expected /= fs
            actual, frequencies = pra.multitaper_psd(signal, nw, fs)
            np.testing.assert_array_equal(actual, expected)
            np.testing.assert_array_equal(frequencies, np.fft.fftfreq(size, 1 / fs))
        self.assertLessEqual(pra.spectral_setup.cache_info().currsize, 8)
        self.assertFalse(pra.spectral_setup(3600, 3.5, 1.)[0].flags.writeable)

    def test_chunk_boundaries_preserve_duplicate_and_missing_sample_semantics(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'raw.iaga2002'
            times = pd.date_range('2026-04-10T19:59:58Z', periods=17000, freq='s')
            rows = ['header\nDATE TIME DOY KAKX KAKY KAKZ KAKF\n']
            rows += [f'{stamp:%Y-%m-%d %H:%M:%S} 100 {i} 4 {99999 if i == 20 else 5} 6\n'
                     for i, stamp in enumerate(times)]
            rows.append(rows[16384])  # duplicate across parser chunks
            path.write_text(''.join(rows))
            full = pra.read_iaga2002(path, ZoneInfo('Asia/Tokyo'))
            start, end = pd.Timestamp('2026-04-10T20:00Z'), pd.Timestamp('2026-04-10T23:00Z')
            filtered = pra.read_iaga2002(path, ZoneInfo('Asia/Tokyo'), start, end)
            expected = full[(full.dt >= start) & (full.dt < end)]
            pd.testing.assert_frame_equal(filtered.reset_index(drop=True), expected.reset_index(drop=True))
            self.assertTrue(filtered.loc[filtered.dt == times[20], 'Z'].isna().all())
            self.assertEqual(len(full), len(times))

    def test_cache_invalidates_on_edits_additions_and_deletions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            file = root / 'data.json'
            file.write_text('one')
            cache = SnapshotCache(max_entries=2, max_bytes=1000)
            calls = []
            def read():
                calls.append(True)
                return {'value': file.read_text() if file.exists() else None}
            revision = lambda: file_revisions(root.glob('*.json'))
            value = cache.get('test', revision(), read)
            value['value'] = 'caller mutation'
            self.assertEqual(cache.get('test', revision(), read), {'value': 'one'})
            self.assertEqual(len(calls), 1)
            file.write_text('two')
            self.assertEqual(cache.get('test', revision(), read), {'value': 'two'})
            (root / 'new.json').write_text('{}')
            cache.get('test', revision(), read)
            file.unlink()
            self.assertEqual(cache.get('test', revision(), read), {'value': None})
            self.assertEqual(len(calls), 4)

    def test_cache_bounds_and_oversized_payload(self):
        cache = SnapshotCache(max_entries=2, max_bytes=64)
        for i in range(20):
            cache.get(i, i, lambda: {'n': i})
        self.assertEqual(len(cache.entries), 2)
        cache.get('large', 1, lambda: {'value': 'x' * 1000})
        self.assertNotIn('large', cache.entries)
        self.assertLessEqual(cache.bytes, 64)


if __name__ == '__main__':
    unittest.main()
