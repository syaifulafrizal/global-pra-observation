"""Retrieve the same adjusted one-second XYZ observations in bounded HAPI chunks.

Official service: https://imag-data.bgs.ac.uk/GIN_V1/
Only the transport/serialization changes; no resampling, gap filling or classification.
"""
import json
import math
import re
import struct
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import requests

BASE_URL = 'https://imag-data.bgs.ac.uk/GIN_V1/hapi'
CHUNK_HOURS = 6
REQUEST_SECONDS = 45
RECORD = struct.Struct('<20sddd')  # HAPI binary: UTC isotime and three little-endian doubles.


class HapiUnavailable(RuntimeError):
    """Unsupported product, invalid response or exhausted network attempts."""


class NoAdjustedData(HapiUnavailable):
    """The service explicitly returned no samples for the entire requested day."""


@dataclass(frozen=True)
class Product:
    fill: float
    start: datetime
    stop: datetime


def _request(endpoint, params, max_bytes, base_url=BASE_URL):
    """Bound both stalled reads and the total transfer; never return partial bodies."""
    for attempt in range(3):
        response = None
        start = time.monotonic()
        try:
            response = requests.get(f'{base_url}/{endpoint}', params=params,
                                    timeout=(8, 15), stream=True)
            if endpoint == 'GINServices' and response.status_code == 400:
                message = response.text
                code = params.get('observatoryIagaCode') or params.get('observatoryIagaCodeList', '')
                if re.search(rf'Unable to find observatory:\s*{re.escape(code)}\b', message):
                    raise NoAdjustedData(f'INTERMAGNET does not provide observatory {code}')
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_content(16384):
                if time.monotonic() - start > REQUEST_SECONDS:
                    raise requests.Timeout('HAPI transfer exceeded its total time budget')
                if len(body) + len(chunk) > max_bytes:
                    raise HapiUnavailable('HAPI response exceeds the expected size limit')
                body.extend(chunk)
            if not response.headers.get('Content-Encoding'):
                length = response.headers.get('Content-Length')
                if length is not None and len(body) != int(length):
                    raise requests.exceptions.ChunkedEncodingError('Incomplete HAPI response')
            return bytes(body)
        except (requests.RequestException, ValueError) as error:
            transient = isinstance(error, (requests.ConnectionError, requests.Timeout,
                                          requests.exceptions.ChunkedEncodingError))
            if isinstance(error, requests.HTTPError) and response is not None:
                transient = response.status_code in (408, 429, 500, 502, 503, 504)
            if not transient or attempt == 2:
                raise HapiUnavailable(str(error)) from error
            print(f'[WARNING] HAPI {params.get("id")}: request failed, retry {attempt + 1}/2: {error}')
            time.sleep(2 ** attempt)
        finally:
            if response is not None:
                response.close()


def _has_adjusted_samples(station, day):
    """An explicit zero in the official directory is not a transport failure."""
    try:
        result = json.loads(_request('GINServices', {
            'Request': 'GetDataDirectory', 'Format': 'json',
            'observatoryIagaCodeList': station, 'samplesPerDay': 'second',
            'dataStartDate': day.strftime('%Y-%m-%d'), 'dataDuration': 1,
            'publicationState': 'adjusted',
        }, 65536, base_url='https://imag-data.bgs.ac.uk/GIN_V1'))
        entries = [entry for entry in result['data'] if entry['iaga_code'] == station
                   and entry['publication_state'] == 'adjusted']
        days = [row for entry in entries for row in entry['days'] if row['date'] == day.strftime('%d-%m-%Y')]
        if len(days) != 1 or type(days[0]['samples_recorded']) is not int or not 0 <= days[0]['samples_recorded'] <= 86400:
            raise HapiUnavailable('Ambiguous INTERMAGNET directory response')
        return days[0]['samples_recorded'] > 0
    except (KeyError, ValueError, TypeError) as error:
        raise HapiUnavailable(f'Invalid INTERMAGNET directory: {error}') from error


def download_legacy(station, day, destination):
    """Keep the original data product/format as a fallback with bounded transfers."""
    body = _request('GINServices', {
        'Request': 'GetData', 'observatoryIagaCode': station, 'samplesPerDay': 'second',
        'dataStartDate': day.strftime('%Y-%m-%d'), 'dataDuration': 1,
        'publicationState': 'adjusted', 'orientation': 'XYZF', 'format': 'iaga2002',
    }, 16 * 1024 * 1024, base_url='https://imag-data.bgs.ac.uk/GIN_V1')
    if not any(line.split()[:3] == ['DATE', 'TIME', 'DOY'] and len(line.split()) >= 6
               for line in body.decode('ascii', errors='replace').splitlines()):
        raise HapiUnavailable('Legacy GIN response is not IAGA-2002 data')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.iaga2002.tmp')
    try:
        temporary.write_bytes(body)
        temporary.replace(destination)
        return destination
    finally:
        if temporary.exists():
            temporary.unlink()


@lru_cache(maxsize=128)
def _metadata(dataset):
    try:
        info = json.loads(_request('info', {'id': dataset}, 65536))
        parameters = {item['name']: item for item in info['parameters']}
        clock, vector = parameters['Time'], parameters['Field_Vector']
        if (info['status']['code'] != 1200 or info.get('cadence') != 'PT1S'
                or clock.get('type') != 'isotime' or clock.get('length') != 20
                or clock.get('units') != 'UTC' or vector.get('type') != 'double'
                or vector.get('size') != [3] or vector.get('units') != ['nT'] * 3
                or vector.get('vectorComponents') != ['x', 'y', 'z']
                or vector.get('coordinateSystemName') != 'Cartesian'):
            raise HapiUnavailable('HAPI metadata does not describe one-second UTC XYZ in nT')
        fill = float(vector['fill'])
        if not math.isfinite(fill):
            raise HapiUnavailable('Invalid HAPI fill value')
        start = datetime.fromisoformat(info['startDate'].replace('Z', '+00:00'))
        stop = datetime.fromisoformat(info['stopDate'].replace('Z', '+00:00'))
        if start.utcoffset() != timedelta(0) or stop.utcoffset() != timedelta(0) or start >= stop:
            raise HapiUnavailable('Invalid HAPI UTC availability range')
        return Product(fill, start, stop)
    except (ValueError, KeyError, TypeError) as error:
        raise HapiUnavailable(f'Invalid HAPI metadata: {error}') from error


def _iaga_number(value, fill):
    if not math.isfinite(value) or value == fill or abs(value) >= 99999:
        return '99999.00'
    # Match the legacy IAGA-2002 service's 0.01-nT serialization precision.
    return str(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def download_iaga(station, day, destination):
    """Build an IAGA-compatible XYZ file only after all four UTC intervals succeed."""
    station = station.upper()
    dataset = f'{station.lower()}/adjusted/PT1S/xyzf'
    try:
        if not _has_adjusted_samples(station, day):
            raise NoAdjustedData(f'No adjusted one-second measurements published for {station} on {day.date()} (directory: 0 samples)')
    except NoAdjustedData:
        raise
    except HapiUnavailable as error:
        # An unavailable directory does not establish that actual data is absent.
        print(f'[WARNING] Could not check INTERMAGNET availability; checking the actual HAPI dataset: {error}')
    product = _metadata(dataset)
    fill = product.fill
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    if product.stop <= start or product.start >= start + timedelta(days=1):
        raise HapiUnavailable('HAPI availability does not overlap a day with recorded directory samples')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.iaga2002.tmp')
    rows = 0
    previous = None
    try:
        with temporary.open('w', encoding='ascii', newline='\n') as output:
            output.write(' Format                 IAGA-2002 |\n')
            output.write(' Source of Data         INTERMAGNET / Edinburgh GIN HAPI |\n')
            output.write(f' IAGA Code              {station} |\n')
            output.write(' Reported               XYZ |\n')
            output.write(' Digital Sampling       1 second |\n')
            output.write(' Data Type              Provisional (adjusted) |\n')
            output.write(f' # Dataset {dataset}; UTC; XYZ nT; legacy precision 0.01 nT |\n')
            output.write(f' # HAPI availability {product.start.isoformat()} to {product.stop.isoformat()} |\n')
            output.write(f'DATE TIME DOY {station}X {station}Y {station}Z\n')
            for hour in range(0, 24, CHUNK_HOURS):
                interval = start + timedelta(hours=hour)
                begin = max(interval, product.start)
                end = min(interval + timedelta(hours=CHUNK_HOURS), product.stop)
                if end <= begin:
                    continue
                body = _request('data', {
                    'id': dataset, 'parameters': 'Time,Field_Vector',
                    'time.min': begin.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'time.max': end.strftime('%Y-%m-%dT%H:%M:%SZ'), 'format': 'binary',
                }, CHUNK_HOURS * 3600 * RECORD.size + 65536)
                if body.lstrip().startswith(b'{'):
                    status = json.loads(body).get('status', {})
                    if status.get('code') == 1201:  # Explicit HAPI no-data response.
                        continue
                    raise HapiUnavailable(f'HAPI returned status {status}')
                if len(body) % RECORD.size:
                    raise HapiUnavailable('Truncated HAPI binary record')
                for text, x, y, z in RECORD.iter_unpack(body):
                    stamp = datetime.fromisoformat(text.decode('ascii').replace('Z', '+00:00'))
                    if (stamp.utcoffset() != timedelta(0) or stamp.microsecond
                            or not begin <= stamp < end or (previous is not None and stamp <= previous)):
                        raise HapiUnavailable('HAPI timestamps are duplicated, unordered or outside the requested UTC interval')
                    previous = stamp
                    values = ' '.join(_iaga_number(value, fill) for value in (x, y, z))
                    output.write(f'{stamp:%Y-%m-%d %H:%M:%S}.000 {stamp:%j} {values}\n')
                    rows += 1
        if not rows:
            raise NoAdjustedData(f'No adjusted one-second XYZ samples for {station} on {start.date()}')
        temporary.replace(destination)
        print(f'[OK] HAPI downloaded {rows} timestamped XYZ samples for {station} {start.date()}')
        return destination
    except (UnicodeError, ValueError, struct.error) as error:
        raise HapiUnavailable(f'Invalid HAPI data: {error}') from error
    finally:
        if temporary.exists():
            temporary.unlink()
