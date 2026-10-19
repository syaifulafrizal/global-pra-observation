#!/usr/bin/env python3
"""Acquire minute-resolution SYM-H from the NASA OMNIWeb service."""

from datetime import datetime, timedelta
from pathlib import Path
import re

import numpy as np
import pandas as pd
import requests

OMNIWEB_URL = 'https://omniweb.gsfc.nasa.gov/cgi/nx1.cgi'
SOURCE = 'OMNI_MIN_SYM_H_41'


def empty_symh():
    return pd.DataFrame(columns=['SYMH', 'Disturbed'],
                        index=pd.DatetimeIndex([], name='Time', tz='UTC'))


def parse_symh_response(text):
    """Parse only YEAR DOY HOUR MINUTE SYM/H, the one requested variable.

    Variable 41 and spacecraft omni_min are specified by NASA's form:
    https://omniweb.gsfc.nasa.gov/form/omni_min.html
    """
    records = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) != 5 or not re.fullmatch(r'\d{4}', fields[0]):
            continue
        try:
            year, doy, hour, minute = map(int, fields[:4])
            value = float(fields[4])
            if not (1 <= doy <= 366 and 0 <= hour < 24 and 0 <= minute < 60):
                continue
            if not np.isfinite(value) or abs(value) >= 99999:
                continue
            timestamp = pd.Timestamp(datetime(year, 1, 1), tz='UTC') + pd.Timedelta(
                days=doy - 1, hours=hour, minutes=minute)
            records.append((timestamp, value))
        except (ValueError, OverflowError):
            continue
    if not records:
        return empty_symh()
    result = pd.DataFrame(records, columns=['Time', 'SYMH']).set_index('Time')
    result = result.sort_index().loc[lambda frame: ~frame.index.duplicated()]
    result['Disturbed'] = result['SYMH'] < -30
    result['Source'] = SOURCE
    return result


def download_symh_omniweb(start_date, end_date, cache_file):
    """Keep the existing API; never reinterpret an unavailable index as quiet."""
    cache_file = Path(cache_file)
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    start = start.tz_localize('UTC') if start.tzinfo is None else start.tz_convert('UTC')
    end = end.tz_localize('UTC') if end.tzinfo is None else end.tz_convert('UTC')
    if start >= end:
        return empty_symh()
    if cache_file.exists():
        try:
            cached = pd.read_csv(cache_file, index_col='Time')
            cached.index = pd.to_datetime(cached.index, utc=True)
            # Old caches used an hourly, unrelated variable. Only reuse data
            # with provenance from this corrected parser and full coverage.
            if (not cached.empty and 'Source' in cached and cached['Source'].eq(SOURCE).all()
                    and cached.index.min() <= start
                    and cached.index.max() >= end - pd.Timedelta(minutes=1)):
                return cached
        except (ValueError, KeyError, OSError):
            pass
    try:
        response = requests.get(OMNIWEB_URL, params={
            'activity': 'retrieve', 'res': 'min', 'spacecraft': 'omni_min',
            'start_date': start.strftime('%Y%m%d'),
            'end_date': end.strftime('%Y%m%d'), 'vars': '41',
        }, timeout=45)
        response.raise_for_status()
        result = parse_symh_response(response.text)
        if result.empty:
            print('[WARNING] NASA returned no usable minute-resolution SYM-H data')
            return result
        result = result.loc[(result.index >= start) & (result.index <= end)]
        if not result.empty:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache_file.with_suffix('.csv.tmp')
            result.to_csv(temporary)
            temporary.replace(cache_file)
        return result
    except (requests.RequestException, ValueError, OSError) as exc:
        print(f'[WARNING] SYM-H unavailable: {exc}')
        return empty_symh()


def download_symh_cdaweb(start_date, end_date, cache_folder):
    """Compatibility wrapper for existing callers."""
    cache_file = Path(cache_folder) / f'SYMH_{start_date:%Y%m%d}_{end_date:%Y%m%d}.csv'
    return download_symh_omniweb(start_date, end_date, cache_file)


if __name__ == '__main__':
    end = datetime.utcnow()
    data = download_symh_cdaweb(end - timedelta(days=3), end,
                               Path('INTERMAGNET_DOWNLOADS') / '_cache')
    print(f'Retrieved {len(data)} SYM-H observations')
