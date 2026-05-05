# GEMPRA Full Source Code Bundle

This document contains the current relevant source files for the GEMPRA platform at the time of preparation for copyright filing.

- Scope: backend processing, frontend interface, serving layer, deployment automation, and dependencies.
- Excludes: generated data files, figures, logs, datasets, and non-source documentation.


---

## logging_utils.py

```python
#!/usr/bin/env python3
"""Logging helpers shared across PRA scripts."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUPS = 10


def _log_dir() -> Path:
    log_dir = Path(os.getenv("PRA_LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _log_path(name: str, run_id: Optional[str]) -> Path:
    prefix = run_id or os.getenv("PRA_RUN_ID")
    filename = f"{name}_{prefix}.log" if prefix else f"{name}.log"
    return _log_dir() / filename


def configure_logger(
    name: str,
    level: Optional[str] = None,
    run_id: Optional[str] = None,
) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    log_level = level or os.getenv("PRA_LOG_LEVEL", "INFO")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    log_file = _log_path(name, run_id)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=int(os.getenv("PRA_LOG_MAX_BYTES", DEFAULT_MAX_BYTES)),
        backupCount=int(os.getenv("PRA_LOG_BACKUPS", DEFAULT_BACKUPS)),
        encoding="utf-8",
    )
    formatter = logging.Formatter(LOG_FORMAT)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    logger.debug("Logger configured: %s", log_file)
    return logger


def attach_stdout_logger(logger: logging.Logger) -> None:
    """Redirect built-in print statements to the structured logger."""
    import builtins

    def _logged_print(*args, **kwargs):  # noqa: ANN001
        sep = kwargs.pop("sep", " ")
        end = kwargs.pop("end", "\n")
        message = sep.join(str(arg) for arg in args) + end
        text = message.rstrip()

        normalized = text.upper()
        if normalized.startswith("[ERROR") or normalized.startswith("ERROR"):
            level = logging.ERROR
        elif normalized.startswith("[WARNING"):
            level = logging.WARNING
        elif normalized.startswith("[SKIP]"):
            level = logging.INFO
        elif normalized.startswith("[OK]"):
            level = logging.INFO
        elif normalized.startswith("[INFO]"):
            level = logging.INFO
        else:
            level = logging.DEBUG
        logger.log(level, text)

    builtins.print = _logged_print
    logger.debug("stdout redirected to %s", logger.name)
```

---

## pra_nighttime.py

```python
#!/usr/bin/env python3
"""
Nighttime PRA Detection for Multiple INTERMAGNET Stations
Uses Multitaper + EVT + nZ z-score method for anomaly detection
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import requests
from scipy import signal
from scipy.stats import genpareto
from scipy.signal import windows
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from logging_utils import configure_logger, attach_stdout_logger

# Configuration
BASE_URL = 'https://imag-data.bgs.ac.uk:443/GIN_V1/GINServices'
OMNI_BASE_URL = 'https://omniweb.gsfc.nasa.gov/cgi/nx1.cgi'
RUN_TIMEZONE = ZoneInfo('Asia/Singapore')  # GMT+8 for Singapore

# Station timezone cache (loaded from stations.json per station)
_station_timezones = {}
SAMPLE_RATE = 'second'
FS = 1  # Hz
WIN_LEN = 3600  # 1-hour window in seconds
STEP = 3600  # 1-hour step
F_LOW = 0.095  # Hz
F_HIGH = 0.110  # Hz
MT_NW = 3.5  # Multitaper time-half bandwidth product

# Analysis options
OPTS = {
    'Fs': FS,           # Sampling frequency
    'winLen': WIN_LEN,  # Window length
    'useMT': True,
    'mtNW': MT_NW,
    'useEVT': True,
    'tailQ': 0.75,
    'fprTarget': 0.05,
    'kSigma': 4.0,
    'pFloor': 0.0,  # No minimum threshold floor - let EVT determine threshold naturally
    'useNZz': True,
    'NZzMin': 1.25,
    'NZfixed': 2.5,
    'usePersist': False,
    'persistK': 2,
    'persistDays': 2,
    'quietTol': 0.05,
    'tightQuiet': False,
    'quietSymh': -30,
    'quietTolTight': 0.02,
    'quietGuardHrs': 0,
    'ltStart': 20,  # Local time start (20:00)
    'ltEnd': 4,     # Local time end (04:00)
}

# Default stations
DEFAULT_STATIONS = ['KAK']

# Run + logging setup
RUN_ID = os.getenv('PRA_RUN_ID') or datetime.utcnow().strftime('%Y%m%d%H%M%S')
os.environ['PRA_RUN_ID'] = RUN_ID
LOGGER = configure_logger('pra_nighttime', run_id=RUN_ID)
attach_stdout_logger(LOGGER)
RUN_REPORT_DIR = Path('data') / 'run_reports'

def get_data_folder(station_code):
    """Get data folder path for a station"""
    return Path('INTERMAGNET_DOWNLOADS') / station_code

def get_station_timezone(station_code):
    """Get timezone for a station from stations.json"""
    global _station_timezones
    
    # Check cache first
    if station_code in _station_timezones:
        return _station_timezones[station_code]
    
    # Try to load from stations.json
    stations_file = Path('stations.json')
    if not stations_file.exists():
        # Fallback to default
        default_tz = ZoneInfo('UTC')
        _station_timezones[station_code] = default_tz
        print(f'[WARNING] stations.json not found, using UTC for {station_code}')
        return default_tz
    
    try:
        with open(stations_file, 'r') as f:
            data = json.load(f)
        
        # Find station in list
        stations = data.get('stations', [])
        for station in stations:
            if station.get('code') == station_code:
                tz_str = station.get('timezone', 'UTC')
                tz = ZoneInfo(tz_str)
                _station_timezones[station_code] = tz
                print(f'[INFO] Using timezone {tz_str} for station {station_code}')
                return tz
        
        # Station not found, use UTC
        default_tz = ZoneInfo('UTC')
        _station_timezones[station_code] = default_tz
        print(f'[WARNING] Station {station_code} not found in stations.json, using UTC')
        return default_tz
    except Exception as e:
        print(f'[WARNING] Error loading timezone for {station_code}: {e}, using UTC')
        default_tz = ZoneInfo('UTC')
        _station_timezones[station_code] = default_tz
        return default_tz

def download_symh_data(start_date, end_date, cache_folder):
    """Download SYM-H geomagnetic index data from OMNIWeb"""
    from download_symh import download_symh_omniweb
    
    cache_file = cache_folder / f'SYMH_{start_date.strftime("%Y%m%d")}_{end_date.strftime("%Y%m%d")}.csv'
    
    # Check cache first
    if cache_file.exists():
        try:
            df = pd.read_csv(cache_file, parse_dates=['Time'], index_col='Time')
            if not df.empty:
                return df
        except:
            pass
    
    # Download from OMNIWeb
    try:
        return download_symh_omniweb(start_date, end_date, cache_file)
    except Exception as e:
        print(f'Warning: SYM-H download failed: {e}')
        # Return empty DataFrame - code will handle this gracefully
        return pd.DataFrame(columns=['SYMH', 'Disturbed'])

def download_data(station_code, date, out_folder):
    """Download IAGA2002 data from INTERMAGNET for a specific date"""
    date_str = date.strftime('%Y-%m-%d')
    out_file = out_folder / f'{station_code}_{date.strftime("%Y%m%d")}.iaga2002'
    
    # Check if file already exists and is not empty
    if out_file.exists() and out_file.stat().st_size > 0:
        print(f'[SKIP] Data already exists for {station_code} on {date_str}')
        return out_file
    
    params = [
        "Request=GetData",
        f"observatoryIagaCode={station_code}",
        f"samplesPerDay={SAMPLE_RATE}",
        f"dataStartDate={date_str}",
        "dataDuration=1",
        "publicationState=adjusted",
        "orientation=native",
        "format=iaga2002"
    ]
    
    url = BASE_URL + "?" + "&".join(params)
    print(f'Downloading {station_code} data for: {date_str}')
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, 'wb') as f:
            f.write(response.content)
        return out_file
    except Exception as e:
        print(f'Warning: Download failed for {date_str}: {e}')
        return None

def read_iaga2002(file_path, station_timezone):
    """Read IAGA2002 format file and return DataFrame
    
    Args:
        file_path: Path to IAGA2002 file
        station_timezone: ZoneInfo object for the station's local timezone
    """
    try:
        # Read header to get metadata
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            header_lines = [f.readline() for _ in range(26)]
        
        # Read data (skip 26 header lines)
        df = pd.read_csv(
            file_path,
            skiprows=26,
            delim_whitespace=True,
            header=None,
            names=['date', 'time', 'doy', 'X', 'Y', 'Z', 'F'],
            usecols=['date', 'time', 'X', 'Y', 'Z']
        )
        
        # Combine date and time
        df['dt'] = pd.to_datetime(df['date'] + ' ' + df['time'], 
                                  format='%Y-%m-%d %H:%M:%S.%f',
                                  errors='coerce')
        # Convert from UTC (data is always in UTC) to station's local timezone
        df['dt'] = df['dt'].dt.tz_localize('UTC').dt.tz_convert(station_timezone)
        
        # Keep only valid data
        df = df[['dt', 'X', 'Y', 'Z']].copy()
        df = df.dropna()
        
        return df
    except Exception as e:
        print(f'Error reading {file_path}: {e}')
        return pd.DataFrame()

def multitaper_psd(data, NW=3.5, Fs=1.0):
    """Compute multitaper power spectral density"""
    N = len(data)
    nw = NW
    k = int(2 * nw - 1)  # Number of tapers
    
    # Generate DPSS (Slepian) sequences
    tapers, eigenvalues = windows.dpss(N, nw, k, return_ratios=True)
    
    # Compute multitaper estimate
    psd = np.zeros(N)
    for i in range(k):
        tapered = data * tapers[i]
        fft_tapered = np.fft.fft(tapered)
        psd += np.abs(fft_tapered)**2 * eigenvalues[i]
    
    psd /= k
    psd /= Fs  # Normalize by sampling frequency
    
    # Frequency vector
    f = np.fft.fftfreq(N, 1/Fs)
    
    return psd, f

def compute_pseries(recXYZ, tUTC_start, tLocal_start, sUTC, eUTC, GI, f_low, f_high, opts):
    """Compute P series per hour using multitaper method"""
    Fs = opts['Fs']
    winLen = opts['winLen']
    step = winLen
    N = winLen
    
    T_list = []
    S_Z_list = []
    S_G_list = []
    
    # Precompute disturbed mask
    isDistMinute, tDist = disturbed_mask(GI, opts['tightQuiet'], opts['quietSymh'])
    
    if opts['quietGuardHrs'] > 0:
        guardMin = opts['quietGuardHrs'] * 60
        isDistMinute = apply_guard(isDistMinute, guardMin)
    
    for s in range(0, len(recXYZ) - winLen + 1, step):
        e = s + winLen
        mid_time_utc = tUTC_start + timedelta(seconds=(s+e)/2 - 1)
        
        if mid_time_utc < sUTC or mid_time_utc > eUTC:
            continue
        
        # Local night gate
        mid_time_local = tLocal_start + timedelta(seconds=(s+e)/2 - 1)
        hr = mid_time_local.hour
        
        isNight = False
        if opts['ltStart'] < opts['ltEnd']:
            isNight = opts['ltStart'] <= hr < opts['ltEnd']
        else:
            isNight = hr >= opts['ltStart'] or hr < opts['ltEnd']
        
        if not isNight:
            continue
        
        seg = recXYZ[s:e, :]
        
        # Ensure seg is a numpy array with numeric dtype
        if hasattr(seg, 'values'):
            seg = seg.values
        seg = np.asarray(seg, dtype=np.float64)
        
        # NaN handling
        nanFrac = np.sum(np.isnan(seg)) / seg.size
        if nanFrac > 0.05:
            continue
        elif nanFrac > 0:
            # Interpolate NaN values
            for c in range(3):
                seg_series = pd.Series(seg[:, c])
                seg_series = seg_series.interpolate(method='linear').bfill().ffill()
                seg[:, c] = seg_series.values
        
        # Extract Z and G components
        segZ = seg[:, 2]
        segG = np.hypot(seg[:, 0], seg[:, 1])
        
        # Spectral estimation
        if opts['useMT']:
            try:
                PZ, fZ = multitaper_psd(segZ, NW=opts['mtNW'], Fs=Fs)
                PG, fG = multitaper_psd(segG, NW=opts['mtNW'], Fs=Fs)
                
                idxZ = (fZ >= f_low) & (fZ <= f_high) & (fZ >= 0)
                idxG = (fG >= f_low) & (fG <= f_high) & (fG >= 0)
                
                # Integrate using trapezoidal rule
                sz = np.trapz(PZ[idxZ], fZ[idxZ])
                sg = np.trapz(PG[idxG], fG[idxG])
            except:
                # Fallback to FFT
                Z = np.fft.fft(segZ, N)
                G = np.fft.fft(segG, N)
                halfIdx = np.arange(1, N//2 + 1)
                PSDz = (np.abs(Z[halfIdx])**2) / N
                PSDg = (np.abs(G[halfIdx])**2) / N
                f = np.arange(N) * (Fs / N)
                f = f[halfIdx]
                idx = (f >= f_low) & (f <= f_high)
                sz = np.sum(PSDz[idx])
                sg = np.sum(PSDg[idx])
        else:
            # Standard FFT
            Z = np.fft.fft(segZ, N)
            G = np.fft.fft(segG, N)
            halfIdx = np.arange(1, N//2 + 1)
            PSDz = (np.abs(Z[halfIdx])**2) / N
            PSDg = (np.abs(G[halfIdx])**2) / N
            f = np.arange(N) * (Fs / N)
            f = f[halfIdx]
            idx = (f >= f_low) & (f <= f_high)
            sz = np.sum(PSDz[idx])
            sg = np.sum(PSDg[idx])
        
        T_list.append(mid_time_utc)
        S_Z_list.append(sz)
        S_G_list.append(sg)
    
    if len(S_Z_list) == 0:
        return None, None, None, None, None, None
    
    S_Z = np.array(S_Z_list)
    S_G = np.array(S_G_list)
    T = pd.Series(T_list)
    
    # For nighttime monitoring (8 hourly windows per day), min-max normalization
    # is statistically unstable and disturbs the analysis. Apply EVT directly to
    # the polarization ratio without normalization, preserving physical scale.
    # This makes thresholds comparable across nights.
    nZ = S_Z  # Keep raw band power for nZ guard (backward compatibility)
    nG = S_G  # Keep raw band power for output (backward compatibility)
    
    # Compute polarization ratio directly from raw band powers
    # Avoid division by zero or near-zero values
    # Use a threshold based on a small fraction of mean S_G to handle cases where S_G is very close to 0
    # This prevents numerical instability while preserving the physical meaning
    mean_S_G = np.mean(S_G[S_G > 0]) if np.any(S_G > 0) else 1.0
    min_S_G = max(1e-10, mean_S_G * 1e-6)  # Use 1e-6 of mean or 1e-10, whichever is larger
    S_G_safe = np.where(S_G > min_S_G, S_G, min_S_G)
    P = S_Z / S_G_safe
    
    # Log warning if many values were clamped (indicates potential data quality issue)
    clamped_count = np.sum(S_G <= min_S_G)
    if clamped_count > 0:
        print(f'  Warning: {clamped_count}/{len(S_G)} S_G values were very small (<= {min_S_G:.2e}) and clamped to prevent division issues')
    
    # Compute quiet flags
    isQuiet, fracDist = compute_quiet_flags(T, GI, opts['quietTol'], opts['tightQuiet'], 
                                           opts['quietTolTight'], opts['quietSymh'])
    
    return P, nZ, nG, T, isQuiet, fracDist

def disturbed_mask(GI, tight, symhThr):
    """Create disturbed mask from SYM-H index"""
    if GI.empty:
        return np.array([]), pd.DatetimeIndex([])
    
    tvec = GI.index
    if tight:
        mask = GI['SYMH'] < symhThr
    else:
        mask = GI['SYMH'] < -30
    
    return mask.values, tvec

def apply_guard(mask, guardMin):
    """Dilate disturbed minutes by Â±guardMin"""
    if guardMin <= 0:
        return mask
    
    out = mask.copy()
    idx = np.where(mask)[0]
    
    for k in idx:
        a = max(0, k - guardMin)
        b = min(len(mask), k + guardMin + 1)
        out[a:b] = True
    
    return out

def compute_quiet_flags(T, GI, tol, tightFlag, tolTight, symhThr):
    """Compute quiet flags based on SYM-H disturbance fraction"""
    isQuiet = np.zeros(len(T), dtype=bool)
    fracDisturbed = np.full(len(T), np.nan)
    
    halfHour = timedelta(minutes=30)
    
    # If GI is empty, assume all periods are quiet (fallback)
    if GI.empty:
        print('Warning: No SYM-H data available. Assuming all periods are quiet.')
        isQuiet[:] = True
        fracDisturbed[:] = 0.0
        return isQuiet, fracDisturbed
    
    for m in range(len(T)):
        time_window_start = T.iloc[m] - halfHour
        time_window_end = T.iloc[m] + halfHour
        
        # Get GI data in window
        try:
            mask = (GI.index >= time_window_start) & (GI.index <= time_window_end)
            GI_subset = GI[mask]
            
            if len(GI_subset) > 0:
                # Recompute disturbed using threshold
                d = GI_subset['SYMH'] < symhThr
                frac = d.mean()
                fracDisturbed[m] = frac
                
                if tightFlag:
                    isQuiet[m] = frac <= tolTight
                else:
                    isQuiet[m] = frac <= tol
            else:
                # No data in window - assume quiet
                isQuiet[m] = True
                fracDisturbed[m] = 0.0
        except Exception as e:
            # On error, assume quiet
            isQuiet[m] = True
            fracDisturbed[m] = 0.0
    
    return isQuiet, fracDisturbed

def fit_evt_threshold(Pq, tailQ, fpr, pFloor, kSigma):
    """Fit EVT (GPD) threshold"""
    Pq = Pq[np.isfinite(Pq)]
    
    if len(Pq) < 20:
        return fit_ksigma_threshold(Pq, kSigma, pFloor)
    
    # Tail over threshold
    u = np.quantile(Pq, tailQ)
    X = Pq[Pq > u] - u
    
    if len(X) < 30:
        return fit_ksigma_threshold(Pq, kSigma, pFloor)
    
    # Fit GPD
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            k, sigma, loc = genpareto.fit(X, floc=0)
        
        # Guard bad shapes
        if not (np.isfinite(k) and np.isfinite(sigma) and sigma > 0 and k > -0.5):
            return fit_ksigma_threshold(Pq, kSigma, pFloor)
        
        # Target (1 - fpr) quantile in tail
        qTail = genpareto.ppf(1 - fpr, k, scale=sigma, loc=0)
        
        if not (np.isfinite(qTail) and qTail >= 0):
            return fit_ksigma_threshold(Pq, kSigma, pFloor)
        
        thr = u + qTail
        # Only apply floor if it's positive (0.0 means no floor)
        if pFloor > 0:
            thr = max(thr, pFloor)
        return thr
    except:
        return fit_ksigma_threshold(Pq, kSigma, pFloor)

def fit_ksigma_threshold(Pq, K, pFloor):
    """Fit k-sigma threshold"""
    Pq = Pq[np.isfinite(Pq)]
    if len(Pq) == 0:
        # Only return floor if it's positive, otherwise return 0
        return pFloor if pFloor > 0 else 0.0
    
    mu = np.mean(Pq)
    sd = np.std(Pq)
    # Only apply floor if it's positive (0.0 means no floor)
    if pFloor > 0:
        return max(mu + K * sd, pFloor)
    return mu + K * sd

def nz_guard(nZ, station, stMap, useZ, zMin, fixedMin):
    """Apply nZ z-score guard"""
    if not useZ:
        return nZ > fixedMin
    
    key = str(station)
    if not stMap or key not in stMap:
        return nZ > fixedMin
    
    mu, sd = stMap[key]
    if sd <= 0:
        sd = np.finfo(float).eps
    
    z = (nZ - mu) / sd
    return z > zMin

def persistence_rule(T, isAnomQuiet, eq_date, K, Ddays):
    """Apply persistence rule"""
    if not np.any(isAnomQuiet):
        return False
    
    t0 = eq_date - timedelta(days=Ddays)
    idx = (T >= t0) & (T <= eq_date)
    return np.sum(isAnomQuiet & idx) >= K

def load_historical_quiet_p_values(station_code, current_date, out_folder, days_back=6):
    """Load quiet P values from past days for EVT fitting
    
    Args:
        station_code: Station code
        current_date: Current date (datetime object in station timezone)
        out_folder: Output folder path
        days_back: Number of past days to load (default 6, for 7 days total including current)
    
    Returns:
        tuple: (numpy array of quiet P values from past days, number of days loaded)
    """
    historical_Pq = []
    days_loaded = 0
    
    for i in range(1, days_back + 1):  # Go back 1 to 6 days
        past_date = current_date - timedelta(days=i)
        json_file = out_folder / f'PRA_Night_{station_code}_{past_date.strftime("%Y%m%d")}.json'
        
        if json_file.exists():
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                
                # Extract P values and isQuiet flags (preferred) or isAnomalous flags (fallback)
                if 'P' in data:
                    P_values = np.array(data['P'])
                    
                    # Prefer isQuiet if available, otherwise use ~isAnomalous as proxy
                    if 'isQuiet' in data:
                        is_quiet = np.array(data['isQuiet'])
                        quiet_mask = is_quiet
                    elif 'isAnomalous' in data:
                        # Fallback: use non-anomalous as quiet proxy
                        is_anomalous = np.array(data['isAnomalous'])
                        quiet_mask = ~is_anomalous
                    else:
                        # If neither available, skip this day
                        continue
                    
                    Pq_day = P_values[quiet_mask & np.isfinite(P_values)]
                    
                    if len(Pq_day) > 0:
                        historical_Pq.extend(Pq_day.tolist())
                        days_loaded += 1
                        print(f'  Loaded {len(Pq_day)} quiet P values from {past_date.date()}')
            except Exception as e:
                print(f'  Warning: Could not load historical data from {past_date.date()}: {e}')
                continue
    
    historical_array = np.array(historical_Pq) if historical_Pq else np.array([])
    return historical_array, days_loaded

def analyze_row(recXYZ, tUTC_start, tLocal_start, eq_date, sUTC, eUTC, GI, 
                f_low, f_high, stationZstats, opts, station_code, historical_Pq=None):
    """Analyze a single row with new method
    
    Args:
        historical_Pq: Optional numpy array of quiet P values from past days for EVT fitting
    """
    # Compute P series
    result = compute_pseries(recXYZ, tUTC_start, tLocal_start, sUTC, eUTC, GI, 
                            f_low, f_high, opts)
    
    if result[0] is None:
        return False, pd.DataFrame(), pd.DataFrame(), np.nan, 0
    
    P, nZ, nG, T, isQuiet, fracDist = result
    
    # Get quiet P values from current day
    Pq_current = P[isQuiet & np.isfinite(P)]
    
    # Combine with historical quiet P values if available
    if historical_Pq is not None and len(historical_Pq) > 0:
        # Combine current day's quiet P values with historical data
        Pq_combined = np.concatenate([historical_Pq, Pq_current])
        print(f'  Using {len(historical_Pq)} historical + {len(Pq_current)} current = {len(Pq_combined)} total quiet P values for EVT fitting')
        print(f'  (Data from historical datapoints + current day)')
    else:
        # Fallback to current day only if no historical data
        Pq_combined = Pq_current
        if len(Pq_current) > 0:
            print(f'  Using {len(Pq_current)} current day quiet P values only (no historical data available yet)')
            print(f'  Note: As more days of data accumulate, the threshold will become more accurate')
    
    if len(Pq_combined) == 0:
        return False, pd.DataFrame(), pd.DataFrame(), np.nan, 0
    
    # Fit threshold using combined 7-day dataset
    if opts['useEVT']:
        thrEff = fit_evt_threshold(Pq_combined, opts['tailQ'], opts['fprTarget'], 
                                   opts['pFloor'], opts['kSigma'])
    else:
        thrEff = fit_ksigma_threshold(Pq_combined, opts['kSigma'], opts['pFloor'])
    
    # nZ guard
    nzOK = nz_guard(nZ, station_code, stationZstats, opts['useNZz'], 
                   opts['NZzMin'], opts['NZfixed'])
    
    isAnomQuiet = (P > thrEff) & isQuiet & nzOK
    
    if opts['usePersist']:
        ok = persistence_rule(T, isAnomQuiet, eq_date, opts['persistK'], opts['persistDays'])
        is_anomalous = ok
    else:
        is_anomalous = np.any(isAnomQuiet)
    
    nAnomHours = np.sum(isAnomQuiet)
    
    # Create timetable
    ts = pd.DataFrame({
        'Time': T.values,
        'P': P,
        'nZ': nZ,
        'nG': nG,
        'isAnomalous': isAnomQuiet,
        'isQuiet': isQuiet  # Store isQuiet for future historical data loading
    })
    ts['Time'] = pd.to_datetime(ts['Time'])
    
    # Anomaly table
    idx = np.where(isAnomQuiet)[0]
    if len(idx) == 0:
        anom_table = pd.DataFrame()
    else:
        anom_times = T.iloc[idx]
        anom_values = P[idx]
        anom_nZ = nZ[idx]
        anom_days = (anom_times - eq_date).dt.total_seconds() / 86400
        
        anom_table = pd.DataFrame({
            'TimeOfAnomaly': anom_times.values,
            'DayOfAnomaly': anom_days.values,
            'AnomalyValue': anom_values,
            'nZ': anom_nZ,
            'ThresholdValue': thrEff
        })
    
    return is_anomalous, anom_table, ts, thrEff, nAnomHours

def cleanup_downloaded_files(out_folder):
    """Delete downloaded IAGA2002 files after processing"""
    iaga_files = list(out_folder.glob('*.iaga2002'))
    for f in iaga_files:
        try:
            f.unlink()
            print(f'Deleted: {f.name}')
        except Exception as e:
            print(f'Warning: Could not delete {f.name}: {e}')

def cleanup_old_data_files(station_code, current_date, out_folder, days_to_keep=7):
    """Clean up old JSON, CSV, and figure files, keeping only the last N days
    
    Args:
        station_code: Station code
        current_date: Current date (datetime object in station timezone)
        out_folder: Output folder path
        days_to_keep: Number of days to keep (default 7, for 7-day rolling window)
    """
    cutoff_date = current_date - timedelta(days=days_to_keep)
    deleted_count = 0
    
    # Clean up JSON files
    json_files = list(out_folder.glob(f'PRA_Night_{station_code}_*.json'))
    for json_file in json_files:
        # Extract date from filename: PRA_Night_{station}_{YYYYMMDD}.json
        try:
            date_str = json_file.stem.split('_')[-1]  # Get YYYYMMDD part
            file_date = datetime.strptime(date_str, '%Y%m%d').date()
            file_date_dt = datetime.combine(file_date, datetime.min.time()).replace(tzinfo=current_date.tzinfo)
            
            if file_date_dt < cutoff_date:
                json_file.unlink()
                deleted_count += 1
                print(f'  Deleted old JSON: {json_file.name}')
        except (ValueError, IndexError) as e:
            # Skip files that don't match the expected pattern
            continue
    
    # Clean up CSV files
    csv_files = list(out_folder.glob(f'PRA_Night_{station_code}_*.csv'))
    for csv_file in csv_files:
        try:
            date_str = csv_file.stem.split('_')[-1]
            file_date = datetime.strptime(date_str, '%Y%m%d').date()
            file_date_dt = datetime.combine(file_date, datetime.min.time()).replace(tzinfo=current_date.tzinfo)
            
            if file_date_dt < cutoff_date:
                csv_file.unlink()
                deleted_count += 1
                print(f'  Deleted old CSV: {csv_file.name}')
        except (ValueError, IndexError):
            continue
    
    # Clean up figure files
    fig_folder = out_folder / 'figures'
    if fig_folder.exists():
        fig_files = list(fig_folder.glob(f'PRA_{station_code}_*.png'))
        for fig_file in fig_files:
            try:
                # Extract date from filename: PRA_{station}_{YYYYMMDD}.png
                date_str = fig_file.stem.split('_')[-1]
                file_date = datetime.strptime(date_str, '%Y%m%d').date()
                file_date_dt = datetime.combine(file_date, datetime.min.time()).replace(tzinfo=current_date.tzinfo)
                
                if file_date_dt < cutoff_date:
                    fig_file.unlink()
                    deleted_count += 1
                    print(f'  Deleted old figure: {fig_file.name}')
            except (ValueError, IndexError):
                continue
    
    if deleted_count > 0:
        print(f'[INFO] Cleaned up {deleted_count} old files for {station_code} (keeping last {days_to_keep} days)')

def process_station(station_code):
    """Process a single station"""
    print(f'\n{"="*60}')
    print(f'Processing station: {station_code}')
    print(f'{"="*60}')
    
    # Get station's timezone from stations.json
    station_tz = get_station_timezone(station_code)
    
    out_folder = get_data_folder(station_code)
    out_folder.mkdir(parents=True, exist_ok=True)
    cache_folder = Path('INTERMAGNET_DOWNLOADS') / '_cache'
    
    # Get dates (GMT+8 at 8am) - this is when we run the analysis
    now = datetime.now(RUN_TIMEZONE)
    today = now.date()
    
    if now.hour < 8:
        today = today - timedelta(days=1)
    
    # Create datetime objects in the station's local timezone
    today_dt = datetime.combine(today, datetime.min.time()).replace(tzinfo=station_tz)
    yesterday_dt = today_dt - timedelta(days=1)
    
    # Check if already ran (unless force rerun is requested)
    json_file = out_folder / f'PRA_Night_{station_code}_{today_dt.strftime("%Y%m%d")}.json'
    force_rerun = os.getenv('FORCE_RERUN', '').lower() in ('1', 'true', 'yes')
    if json_file.exists() and not force_rerun:
        print(f'[OK] Analysis already completed for {station_code} on {today_dt.date()}')
        print(f'      (Set FORCE_RERUN=1 to rerun)')
        return True
    elif json_file.exists() and force_rerun:
        print(f'[INFO] Force rerun enabled - reprocessing {station_code} on {today_dt.date()}')
    
    # Download SYM-H data (need wider range for quiet flag computation)
    symh_start = yesterday_dt - timedelta(days=1)
    symh_end = today_dt + timedelta(days=1)
    GI = download_symh_data(symh_start, symh_end, cache_folder)
    
    # Check if the nighttime window has already passed for this station
    # The nighttime window is 20:00 yesterday to 04:00 today (local time)
    start_time = yesterday_dt.replace(hour=20, minute=0, second=0)
    end_time = today_dt.replace(hour=4, minute=0, second=0)
    
    # Get current time in station's timezone
    now_station_tz = datetime.now(station_tz)
    
    # If we're before 04:00 today in station's timezone, the nighttime window hasn't completed yet
    # However, we should still check if yesterday's data exists and download it if missing
    if now_station_tz < end_time:
        print(f'[INFO] Station {station_code} ({station_tz}): Nighttime window not yet complete')
        print(f'       Current time: {now_station_tz.strftime("%Y-%m-%d %H:%M:%S %Z")}')
        print(f'       Window ends:  {end_time.strftime("%Y-%m-%d %H:%M:%S %Z")}')
        
        # Check if yesterday's data exists - if not, download it
        yesterday_file = out_folder / f'{station_code}_{yesterday_dt.strftime("%Y%m%d")}.iaga2002'
        if not yesterday_file.exists() or yesterday_file.stat().st_size == 0:
            print(f'[INFO] Yesterday\'s data missing for {station_code} - downloading...')
            file_path = download_data(station_code, yesterday_dt, out_folder)
            if file_path and file_path.exists():
                print(f'[OK] Downloaded yesterday\'s data for {station_code}')
            else:
                print(f'[WARNING] Could not download yesterday\'s data for {station_code}')
        else:
            print(f'[OK] Yesterday\'s data already exists for {station_code}')
        
        print(f'       Processing will be available after 04:00 local time')
        return None  # Return None to indicate "skipped" (not an error)
    
    # Download station data
    dates_to_get = [yesterday_dt, today_dt]
    data_all = pd.DataFrame()
    downloaded_files = []
    download_failed = False
    
    for date_dt in dates_to_get:
        file_path = download_data(station_code, date_dt, out_folder)
        if file_path and file_path.exists():
            downloaded_files.append(file_path)
            df = read_iaga2002(file_path, station_tz)
            if not df.empty:
                data_all = pd.concat([data_all, df], ignore_index=True)
        elif file_path is None:
            # Download failed - this might be an error or data not available yet
            # Check if this date is in the future for this station
            if date_dt.date() > now_station_tz.date():
                print(f'[SKIP] Data for {date_dt.date()} is in the future for {station_code} ({station_tz})')
            else:
                download_failed = True
    
    if data_all.empty:
        if download_failed:
            print(f'[ERROR] No data available for {station_code} - download failed')
            return False
        else:
            # Data might not be available yet (not yet midnight or data not published)
            print(f'[SKIP] No data available yet for {station_code} ({station_tz})')
            print(f'       This may be normal if it\'s not yet midnight or data is not yet published')
            return None  # Return None to indicate "skipped" (not an error)
    
    # Ensure timezone-aware for filtering (should already be, but double-check)
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=station_tz)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=station_tz)
    
    night_data = data_all[(data_all['dt'] >= start_time) & (data_all['dt'] <= end_time)].copy()
    
    if len(night_data) < WIN_LEN:
        print(f'[WARNING] Not enough nighttime data for {station_code} (got {len(night_data)} samples, need {WIN_LEN})')
        print(f'          This may be normal if the nighttime window is not yet complete')
        return None  # Return None to indicate "skipped" (not an error)
    
    # Remove invalid data
    night_data = night_data[
        night_data['X'].notna() & 
        night_data['Y'].notna() & 
        night_data['Z'].notna()
    ].copy()
    
    recXYZ = night_data[['X', 'Y', 'Z']].values
    
    # Convert times - ensure timezone-aware in station's local timezone
    # Data from read_iaga2002 should already be in station's local timezone, but check to be safe
    if night_data['dt'].dtype.tz is None:
        # Check if first element has timezone
        if night_data['dt'].iloc[0].tzinfo is None:
            night_data['dt'] = night_data['dt'].dt.tz_localize(station_tz)
        else:
            # Series is naive but elements are aware - convert series
            night_data['dt'] = pd.to_datetime(night_data['dt'], utc=True).dt.tz_convert(station_tz)
    else:
        # Series is timezone-aware - ensure it's in station's timezone
        night_data['dt'] = night_data['dt'].dt.tz_convert(station_tz)
    
    # Now get UTC and local times (pandas Timestamp)
    tUTC_start = pd.Timestamp(night_data['dt'].iloc[0]).tz_convert('UTC')
    tLocal_start = pd.Timestamp(night_data['dt'].iloc[0])
    
    # Convert start/end times to UTC (using pandas for consistency)
    sUTC = pd.Timestamp(start_time).tz_convert('UTC')
    eUTC = pd.Timestamp(end_time).tz_convert('UTC')
    eq_date = today_dt
    
    # Station stats (empty for now - can be computed from historical data)
    stationZstats = {}
    
    # Load historical quiet P values from past 6 days for EVT fitting
    print(f'[INFO] Loading historical quiet P values for {station_code}...')
    historical_Pq, days_loaded = load_historical_quiet_p_values(station_code, today_dt, out_folder, days_back=6)
    
    if days_loaded > 0:
        print(f'[INFO] Found historical data from {days_loaded} past day(s) for {station_code}')
    else:
        print(f'[INFO] No historical data available yet for {station_code} - will use current day only')
    
    # Analyze
    is_anomalous, anom_table, ts, thrEff, nAnomHours = analyze_row(
        recXYZ, tUTC_start, tLocal_start, eq_date, sUTC, eUTC, GI,
        F_LOW, F_HIGH, stationZstats, OPTS, station_code, historical_Pq=historical_Pq
    )
    
    if ts.empty:
        print(f'[ERROR] No valid time series for {station_code}')
        return False
    
    # Save results - include isQuiet for future historical data loading
    results = {
        'date': today_dt.date().isoformat(),
        'station': station_code,
        'timestamps': [t.isoformat() for t in ts['Time']],
        'P': ts['P'].tolist(),
        'nZ': ts['nZ'].tolist(),
        'nG': ts['nG'].tolist(),
        'isAnomalous': ts['isAnomalous'].tolist(),
        'isQuiet': ts['isQuiet'].tolist(),  # Store isQuiet for historical data loading
        'threshold': float(thrEff),
        'nAnomHours': int(nAnomHours),
        'is_anomalous': bool(is_anomalous)
    }
    
    # Save JSON
    with open(json_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Save CSV
    csv_file = out_folder / f'PRA_Night_{station_code}_{today_dt.strftime("%Y%m%d")}.csv'
    ts.to_csv(csv_file, index=False)
    
    # Save plot
    fig_file = save_plot(station_code, out_folder, ts, thrEff, today_dt, station_tz)
    
    # Log anomalies
    if is_anomalous and not anom_table.empty:
        log_anomaly(station_code, out_folder, today_dt, yesterday_dt, thrEff,
                   anom_table, ts, fig_file)
    
    # Cleanup downloaded files
    cleanup_downloaded_files(out_folder)
    
    # Cleanup old data files (keep only last 7 days)
    print(f'[INFO] Cleaning up old data files for {station_code}...')
    cleanup_old_data_files(station_code, today_dt, out_folder, days_to_keep=7)
    
    print(f'[OK] PRA Nighttime Analysis Completed for {station_code}')
    return True

def save_plot(station_code, out_folder, ts, thr, date, station_timezone):
    """Generate and save PRA plot
    
    Args:
        station_code: Station code
        out_folder: Output folder
        ts: Time series DataFrame
        thr: Threshold value
        date: Analysis date
        station_timezone: ZoneInfo object for the station's local timezone
    """
    fig_folder = out_folder / 'figures'
    fig_folder.mkdir(parents=True, exist_ok=True)
    
    fig_file = fig_folder / f'PRA_{station_code}_{date.strftime("%Y%m%d")}.png'
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    
    t_utc = pd.to_datetime(ts['Time'])
    P = ts['P'].values
    nZ = ts['nZ'].values
    nG = ts['nG'].values
    anomaly_idx = ts['isAnomalous'].values
    
    # Plot 1: P
    ax1.plot(t_utc, P, 'k-', linewidth=1.2, label='P')
    ax1.axhline(y=thr, color='r', linestyle='--', label='Threshold')
    ax1.scatter(t_utc[anomaly_idx], P[anomaly_idx], 
               c='red', s=50, zorder=5, label='Anomaly')
    ax1.set_xlabel('Time (Local)')
    ax1.set_ylabel('P (nZ/nG)')
    ax1.set_title(f'PRA - {station_code} Nighttime ({date.strftime("%Y-%m-%d")})')
    ax1.legend()
    ax1.grid(True)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=station_timezone))
    
    # Plot 2: nZ and nG (raw band powers, no normalization)
    ax2.plot(t_utc, nZ, 'b-', linewidth=1.2, label='S_Z (raw)')
    ax2.plot(t_utc, nG, 'g--', linewidth=1.2, label='S_G (raw)')
    ax2.set_xlabel('Time (Local)')
    ax2.set_ylabel('Band Power (raw)')
    ax2.legend()
    ax2.grid(True)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=station_timezone))
    
    plt.tight_layout()
    plt.savefig(fig_file, dpi=150, bbox_inches='tight')
    plt.close()
    
    return fig_file

def log_anomaly(station_code, out_folder, date, yesterday, thr, anom_table, ts, fig_file):
    """Log anomaly to master table"""
    log_file = out_folder / 'anomaly_master_table.csv'
    
    # Group anomalies by hour
    anom_times = pd.to_datetime(anom_table['TimeOfAnomaly'])
    anom_hours = anom_times.dt.floor('H').unique()
    time_blocks = []
    for h in anom_hours:
        h_str = h.strftime('%H:%M')
        h_end = (h + pd.Timedelta(hours=1)).strftime('%H:%M')
        time_blocks.append(f'{h_str}â€“{h_end}')
    time_str = ', '.join(time_blocks)
    
    # Prepare row
    range_str = f'{yesterday.strftime("%d/%m/%Y")} 20:00 - {date.strftime("%d/%m/%Y")} 04:00'
    pra_vals = ', '.join([f'{p:.2f}' for p in anom_table['AnomalyValue'].values])
    nz_vals = ', '.join([f'{nz:.2f}' for nz in anom_table['nZ'].values])
    
    # Get nG values for anomalies
    anom_indices = ts['isAnomalous']
    ng_vals = ', '.join([f'{ng:.2f}' for ng in ts.loc[anom_indices, 'nG'].values])
    
    new_row = {
        'Range': range_str,
        'Threshold': thr,
        'PRA': pra_vals,
        'nZ': nz_vals,
        'nG': ng_vals,
        'Remarks': 'Anomaly detected',
        'Times': time_str,
        'Plot': fig_file.name
    }
    
    # Append to CSV
    if log_file.exists():
        df_log = pd.read_csv(log_file)
        df_log = pd.concat([df_log, pd.DataFrame([new_row])], ignore_index=True)
    else:
        df_log = pd.DataFrame([new_row])
    
    df_log.to_csv(log_file, index=False)

def get_all_stations():
    """Get all available station codes from stations.json"""
    try:
        from load_stations import load_stations
        stations_data = load_stations()
        if stations_data:
            return [s['code'] for s in stations_data]
    except ImportError:
        pass
    except Exception as e:
        print(f'Warning: Could not load stations.json: {e}')
    
    # Fallback to default if stations.json not available
    return DEFAULT_STATIONS

def main():
    """Main function"""
    stations_env = os.getenv('INTERMAGNET_STATIONS', '')
    
    if stations_env:
        # User specified stations
        codes = [s.strip() for s in stations_env.split(',')]
        # Optional: Validate station codes
        try:
            from load_stations import validate_station_codes
            valid, invalid = validate_station_codes(codes)
            if invalid:
                print(f'[WARNING] Invalid station codes: {", ".join(invalid)}')
            stations = valid if valid else codes
        except ImportError:
            # If load_stations.py not available, use codes as-is
            stations = codes
    else:
        # Auto-detect: Use all stations from stations.json
        print('No stations specified. Loading all available stations...')
        stations = get_all_stations()
        print(f'Found {len(stations)} stations to process')
    
    print(f'\n{"="*60}')
    print(f'Starting PRA Nighttime Analysis (Multitaper + EVT Method)')
    print(f'Stations ({len(stations)}): {", ".join(stations[:10])}{"..." if len(stations) > 10 else ""}')
    print(f'Run time: {datetime.now(RUN_TIMEZONE)}')
    print(f'{"="*60}\n')
    
    results = {}
    for station in stations:
        try:
            success = process_station(station)
            if success is True:
                results[station] = 'success'
            elif success is None:
                results[station] = 'skipped'  # No data yet (expected)
            else:
                results[station] = 'failed'  # Actual error
        except Exception as e:
            print(f'ERROR: Error processing {station}: {e}')
            import traceback
            traceback.print_exc()
            results[station] = 'error'
    
    print(f'\n{"="*60}')
    print('Summary:')
    for station, status in results.items():
        if status == 'skipped':
            print(f'  {station}: {status} (no data yet - expected)')
        else:
            print(f'  {station}: {status}')
    print(f'{"="*60}')
    
    # Count statistics
    success_count = sum(1 for s in results.values() if s == 'success')
    skipped_count = sum(1 for s in results.values() if s == 'skipped')
    failed_count = sum(1 for s in results.values() if s in ('failed', 'error'))
    
    print(f'\nStatistics:')
    print(f'  Success: {success_count}')
    print(f'  Skipped (no data yet): {skipped_count}')
    print(f'  Failed/Error: {failed_count}')
    print(f'{"="*60}')

if __name__ == '__main__':
    main()
```

---

## earthquake_integration.py

```python
#!/usr/bin/env python3
"""
Earthquake Integration Module
Fetches earthquake data from USGS and correlates with PRA anomalies
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import json
from geopy.distance import geodesic

# USGS Earthquake API
USGS_API_BASE = 'https://earthquake.usgs.gov/fdsnws/event/1/query'

def get_station_coordinates(station_code):
    """Get station coordinates from stations.json"""
    try:
        from load_stations import get_station_info
        info = get_station_info(station_code)
        if info:
            return info['latitude'], info['longitude']
    except:
        pass
    return None, None

def fetch_usgs_earthquakes(start_date, end_date, min_magnitude=4.0, 
                          latitude=None, longitude=None, max_radius_km=200):
    """
    Fetch earthquakes from USGS API
    
    Parameters:
    -----------
    start_date : datetime
        Start date for earthquake search
    end_date : datetime
        End date for earthquake search
    min_magnitude : float
        Minimum earthquake magnitude (default: 4.0)
    latitude : float
        Station latitude (for radius search)
    longitude : float
        Station longitude (for radius search)
    max_radius_km : float
        Maximum radius in km (default: 200)
    
    Returns:
    --------
    pd.DataFrame : Earthquake data
    """
    params = {
        'format': 'geojson',
        'starttime': start_date.strftime('%Y-%m-%d'),
        'endtime': end_date.strftime('%Y-%m-%d'),
        'minmagnitude': min_magnitude,
        'orderby': 'time'
    }
    
    # If coordinates provided, use radius search
    if latitude is not None and longitude is not None and max_radius_km is not None:
        params['latitude'] = latitude
        params['longitude'] = longitude
        params['maxradiuskm'] = max_radius_km
    
    try:
        print(f'Fetching earthquakes from USGS: {start_date.date()} to {end_date.date()}')
        response = requests.get(USGS_API_BASE, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if 'features' not in data or len(data['features']) == 0:
            return pd.DataFrame()
        
        # Parse GeoJSON features
        earthquakes = []
        for feature in data['features']:
            props = feature['properties']
            geom = feature['geometry']['coordinates']
            
            eq = {
                'time': pd.to_datetime(props['time'], unit='ms'),
                'latitude': geom[1],
                'longitude': geom[0],
                'depth': geom[2] if len(geom) > 2 else None,
                'magnitude': props.get('mag', None),
                'place': props.get('place', ''),
                'type': props.get('type', 'earthquake'),
                'id': props.get('id', '')
            }
            earthquakes.append(eq)
        
        df = pd.DataFrame(earthquakes)
        print(f'Found {len(df)} earthquakes')
        return df
        
    except Exception as e:
        print(f'Error fetching earthquakes: {e}')
        return pd.DataFrame()

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in km"""
    return geodesic((lat1, lon1), (lat2, lon2)).kilometers

def find_nearby_earthquakes(station_code, anomaly_date, days_before=14, days_after=0,
                           max_distance_km=200, min_magnitude=4.0):
    """
    Find earthquakes within specified distance and time window
    
    Parameters:
    -----------
    station_code : str
        Station code (e.g., 'KAK')
    anomaly_date : datetime
        Date of PRA anomaly
    days_before : int
        Days before anomaly to search (default: 14)
    days_after : int
        Days after anomaly to search (default: 0)
    max_distance_km : float
        Maximum distance in km (default: 200)
    min_magnitude : float
        Minimum earthquake magnitude (default: 4.0)
    
    Returns:
    --------
    pd.DataFrame : Nearby earthquakes with distances
    """
    # Get station coordinates
    lat, lon = get_station_coordinates(station_code)
    if lat is None or lon is None:
        print(f'Warning: Could not get coordinates for {station_code}')
        return pd.DataFrame()
    
    # Define time window
    start_date = anomaly_date - timedelta(days=days_before)
    end_date = anomaly_date + timedelta(days=days_after)
    
    # Fetch earthquakes
    eq_df = fetch_usgs_earthquakes(start_date, end_date, 
                                   min_magnitude=min_magnitude,
                                   latitude=lat, 
                                   longitude=lon,
                                   max_radius_km=max_distance_km)
    
    if eq_df.empty:
        return pd.DataFrame()
    
    # Calculate distances
    distances = []
    for _, eq in eq_df.iterrows():
        dist = calculate_distance(lat, lon, eq['latitude'], eq['longitude'])
        distances.append(dist)
    
    eq_df['distance_km'] = distances
    eq_df['days_from_anomaly'] = (eq_df['time'] - anomaly_date).dt.total_seconds() / 86400
    
    # Filter by distance
    eq_df = eq_df[eq_df['distance_km'] <= max_distance_km].copy()
    eq_df = eq_df.sort_values('time')
    
    return eq_df

def correlate_anomalies_with_earthquakes(station_code, results_folder):
    """
    Correlate PRA anomalies with nearby earthquakes
    
    Parameters:
    -----------
    station_code : str
        Station code
    results_folder : Path
        Folder containing PRA results
    
    Returns:
    --------
    pd.DataFrame : Correlation results
    """
    # Load anomaly table
    anomaly_file = results_folder / 'anomaly_master_table.csv'
    if not anomaly_file.exists():
        return pd.DataFrame()
    
    try:
        anomalies = pd.read_csv(anomaly_file)
    except:
        return pd.DataFrame()
    
    if anomalies.empty:
        return pd.DataFrame()
    
    # Process each anomaly
    correlations = []
    
    for _, anomaly in anomalies.iterrows():
        # Parse date from Range column
        try:
            # Format: "DD/MM/YYYY 20:00 - DD/MM/YYYY 04:00"
            date_str = anomaly['Range'].split()[0]  # First date
            anomaly_date = pd.to_datetime(date_str, format='%d/%m/%Y')
        except:
            continue
        
        # Find nearby earthquakes
        eq_df = find_nearby_earthquakes(station_code, anomaly_date,
                                       days_before=14, days_after=0,
                                       max_distance_km=200, min_magnitude=4.0)
        
        if not eq_df.empty:
            # Filter for magnitude >= 5.0 for reliability assessment
            eq_df_reliable = eq_df[eq_df['magnitude'] >= 5.0].copy()
            
            if not eq_df_reliable.empty:
                # Get closest earthquake with magnitude >= 5.0
                closest = eq_df_reliable.loc[eq_df_reliable['distance_km'].idxmin()]
                
                correlation = {
                    'anomaly_date': anomaly_date,
                    'anomaly_range': anomaly['Range'],
                    'anomaly_times': anomaly.get('Times', ''),
                    'earthquake_time': closest['time'],
                    'earthquake_magnitude': closest['magnitude'],
                    'earthquake_distance_km': closest['distance_km'],
                    'earthquake_place': closest['place'],
                    'days_before_anomaly': closest['days_from_anomaly'],
                    'total_earthquakes': len(eq_df),
                    'reliable_earthquakes': len(eq_df_reliable),
                    'status': 'TP'  # True Positive: Anomaly followed by EQ
                }
                correlations.append(correlation)
            else:
                # Anomaly + No Reliable EQ (>=5.0) nearby = False Positive
                # BUT we must ensure 14 days have actually passed before calling it FP
                days_since_anomaly = (datetime.now().date() - anomaly_date.date()).days
                status = 'FP' if days_since_anomaly >= 14 else 'Pending'
                
                correlation = {
                    'anomaly_date': anomaly_date,
                    'anomaly_range': anomaly['Range'],
                    'anomaly_times': anomaly.get('Times', ''),
                    'earthquake_time': None,
                    'earthquake_magnitude': None,
                    'earthquake_distance_km': None,
                    'earthquake_place': None,
                    'days_before_anomaly': None,
                    'total_earthquakes': 0,
                    'reliable_earthquakes': 0,
                    'status': status
                }
                correlations.append(correlation)
        else:
            # No EQ at all found
            days_since_anomaly = (datetime.now().date() - anomaly_date.date()).days
            status = 'FP' if days_since_anomaly >= 14 else 'Pending'
            
            correlation = {
                'anomaly_date': anomaly_date,
                'anomaly_range': anomaly['Range'],
                'anomaly_times': anomaly.get('Times', ''),
                'earthquake_time': None,
                'earthquake_magnitude': None,
                'earthquake_distance_km': None,
                'earthquake_place': None,
                'days_before_anomaly': None,
                'total_earthquakes': 0,
                'reliable_earthquakes': 0,
                'status': status
            }
            correlations.append(correlation)

    if correlations:
        return pd.DataFrame(correlations)
    return pd.DataFrame()

def find_false_negatives(station_code, results_folder, days_lookback=14):
    """
    Find false negatives: Earthquakes with magnitude >= 5.0 that occurred 
    but no anomaly was detected
    
    Parameters:
    -----------
    station_code : str
        Station code
    results_folder : Path
        Folder containing PRA results
    days_lookback : int
        Number of days to look back for earthquakes (default: 14)
    
    Returns:
    --------
    pd.DataFrame : False negative earthquakes
    """
    # Get station coordinates
    lat, lon = get_station_coordinates(station_code)
    if lat is None or lon is None:
        return pd.DataFrame()
    
    # Get date range from latest processed data
    json_files = list(results_folder.glob('PRA_Night_*.json'))
    if not json_files:
        return pd.DataFrame()
    
    # Get latest processing date
    latest_json = max(json_files, key=lambda p: p.stat().st_mtime)
    try:
        with open(latest_json, 'r') as f:
            data = json.load(f)
            if 'date' in data:
                latest_date = pd.to_datetime(data['date'])
            else:
                latest_date = datetime.now()
    except:
        latest_date = datetime.now()
    
    # Define time window
    end_date = latest_date
    start_date = end_date - timedelta(days=days_lookback)
    
    # Fetch all earthquakes with magnitude >= 5.0
    eq_df = fetch_usgs_earthquakes(start_date, end_date,
                                   min_magnitude=5.0,
                                   latitude=lat,
                                   longitude=lon,
                                   max_radius_km=200)
    
    if eq_df.empty:
        return pd.DataFrame()
    
    # Calculate distances
    distances = []
    for _, eq in eq_df.iterrows():
        dist = calculate_distance(lat, lon, eq['latitude'], eq['longitude'])
        distances.append(dist)
    
    eq_df['distance_km'] = distances
    eq_df = eq_df[eq_df['distance_km'] <= 200].copy()
    
    # Check which earthquakes had no corresponding anomaly
    anomaly_file = results_folder / 'anomaly_master_table.csv'
    anomaly_dates = []
    
    if anomaly_file.exists():
        try:
            anomalies = pd.read_csv(anomaly_file)
            for _, anomaly in anomalies.iterrows():
                try:
                    date_str = anomaly['Range'].split()[0]
                    anomaly_date = pd.to_datetime(date_str, format='%d/%m/%Y')
                    anomaly_dates.append(anomaly_date.date())
                except:
                    continue
        except:
            pass
    
    # Find earthquakes without corresponding anomalies
    false_negatives = []
    
    # Pre-parse all anomaly dates for this station
    anomaly_dates = []
    if anomaly_file.exists():
        try:
            anomalies = pd.read_csv(anomaly_file)
            for _, anomaly in anomalies.iterrows():
                try:
                    date_str = anomaly['Range'].split()[0]
                    anomaly_date = pd.to_datetime(date_str, format='%d/%m/%Y').date()
                    anomaly_dates.append(anomaly_date)
                except:
                    continue
        except:
            pass
            
    for _, eq in eq_df.iterrows():
        eq_date = eq['time'].date()
        # Definition: False Negative if EQ occurred but NO anomaly was detected in the preceding 14 days
        # (Meaning: We missed it)
        
        has_anomaly_before = False
        for anom_date in anomaly_dates:
            # Check if anomaly occurred 1-14 days BEFORE event
            # Logic: Anomaly (Day T) -> Prediction for [T, T+14]
            # So for an EQ on Day E, we look for Anomaly on [E-14, E]
            days_diff = (eq_date - anom_date).days
            if 0 <= days_diff <= 14:
                has_anomaly_before = True
                break
        
        if not has_anomaly_before:
            false_negatives.append({
                'earthquake_time': eq['time'],
                'earthquake_magnitude': eq['magnitude'],
                'earthquake_distance_km': eq['distance_km'],
                'earthquake_place': eq['place'],
                'earthquake_latitude': eq['latitude'],
                'earthquake_longitude': eq['longitude']
            })
    
    if false_negatives:
        return pd.DataFrame(false_negatives)
    return pd.DataFrame()

def save_earthquake_correlations(station_code, results_folder, correlations_df):
    """Save earthquake correlation results"""
    if correlations_df.empty:
        return
    
    output_file = results_folder / 'earthquake_correlations.csv'
    correlations_df.to_csv(output_file, index=False)
    print(f'Saved earthquake correlations: {output_file}')

def save_false_negatives(station_code, results_folder, false_negatives_df):
    """Save false negative earthquakes"""
    if false_negatives_df.empty:
        return
    
    output_file = results_folder / 'false_negatives.csv'
    false_negatives_df.to_csv(output_file, index=False)
    print(f'Saved false negatives: {output_file}')

def get_global_earthquakes_today(min_magnitude=5.0):
    """
    Get all global earthquakes (magnitude >= min_magnitude) for today
    Used for reporting total earthquake count (not just within 200km)
    
    Parameters:
    -----------
    min_magnitude : float
        Minimum magnitude (default: 5.5)
    
    Returns:
    --------
    pd.DataFrame : All global earthquakes today
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=1)
    
    # Fetch global earthquakes (no location filter)
    eq_df = fetch_usgs_earthquakes(start_date, end_date,
                                  min_magnitude=min_magnitude,
                                  latitude=None,
                                  longitude=None,
                                  max_radius_km=None)
    
    return eq_df

def get_recent_earthquakes_all_stations(days=1, min_magnitude=5.0):
    """
    Get all recent earthquakes (magnitude >= min_magnitude) for all stations
    Used for displaying on map (shows only today's earthquakes within 200km)
    
    Parameters:
    -----------
    days : int
        Number of days to look back (default: 1 for today only)
    min_magnitude : float
        Minimum magnitude (default: 5.5)
    
    Returns:
    --------
    pd.DataFrame : All earthquakes with station associations
    """
    try:
        from load_stations import load_stations
        stations = load_stations()
    except:
        return pd.DataFrame()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    all_earthquakes = []
    
    for station in stations:
        lat = station.get('latitude')
        lon = station.get('longitude')
        if lat is None or lon is None:
            continue
        
        # Fetch earthquakes
        eq_df = fetch_usgs_earthquakes(start_date, end_date,
                                      min_magnitude=min_magnitude,
                                      latitude=lat,
                                      longitude=lon,
                                      max_radius_km=200)
        
        if not eq_df.empty:
            # Calculate distances
            distances = []
            for _, eq in eq_df.iterrows():
                dist = calculate_distance(lat, lon, eq['latitude'], eq['longitude'])
                distances.append(dist)
            
            eq_df['distance_km'] = distances
            eq_df['station_code'] = station['code']
            eq_df['station_name'] = station.get('name', station['code'])
            
            all_earthquakes.append(eq_df)
    
    if all_earthquakes:
        combined = pd.concat(all_earthquakes, ignore_index=True)
        # Remove duplicates (same earthquake near multiple stations)
        combined = combined.drop_duplicates(subset=['time', 'latitude', 'longitude'])
        return combined
    
    return pd.DataFrame()

def main():
    """Test earthquake integration"""
    from load_stations import load_stations
    
    stations = load_stations()
    if not stations:
        print('No stations found')
        return
    
    # Test with first station
    station = stations[0]
    station_code = station['code']
    
    print(f'Testing earthquake integration for {station_code}')
    print(f'Station: {station["name"]}, {station["country"]}')
    print(f'Coordinates: {station["latitude"]}, {station["longitude"]}')
    
    # Test: Find earthquakes in last 30 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    eq_df = fetch_usgs_earthquakes(start_date, end_date,
                                   latitude=station['latitude'],
                                   longitude=station['longitude'],
                                   max_radius_km=200)
    
    if not eq_df.empty:
        print(f'\nFound {len(eq_df)} earthquakes within 200km:')
        print(eq_df[['time', 'magnitude', 'place']].head())
    else:
        print('No earthquakes found in the specified time/radius')

if __name__ == '__main__':
    main()

```

---

## integrate_earthquakes.py

```python
#!/usr/bin/env python3
"""
Integrate earthquake data with PRA anomaly results
Run this after pra_nighttime.py to add earthquake correlations
"""

import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
from load_stations import load_stations
from earthquake_integration import (
    correlate_anomalies_with_earthquakes, 
    save_earthquake_correlations,
    find_false_negatives,
    save_false_negatives,
    get_recent_earthquakes_all_stations
)

def main():
    """Main function to integrate earthquakes for all stations"""
    print('='*60)
    print('Earthquake Integration with PRA Anomalies')
    print('='*60)
    
    # Get all stations
    stations_data = load_stations()
    if not stations_data:
        print('No stations found. Make sure stations.json exists.')
        return
    
    stations = [s['code'] for s in stations_data]
    
    print(f'Processing {len(stations)} stations...\n')
    
    results_summary = {}
    
    for station_code in stations:
        print(f'Processing {station_code}...')
        
        results_folder = Path('INTERMAGNET_DOWNLOADS') / station_code
        
        if not results_folder.exists():
            print(f'  [WARNING] No results folder for {station_code}')
            continue
        
        # Correlate anomalies with earthquakes (magnitude >= 5.0 for reliability)
        correlations = correlate_anomalies_with_earthquakes(station_code, results_folder)
        
        # Find false negatives (EQ >= 5.0 occurred but no anomaly detected)
        false_negatives = find_false_negatives(station_code, results_folder, days_lookback=14)
        
        if not correlations.empty:
            # Save correlations
            save_earthquake_correlations(station_code, results_folder, correlations)
            print(f'  [OK] Found {len(correlations)} anomaly-earthquake correlations (M>=5.0)')
        else:
            print(f'  [INFO] No earthquake correlations found (M>=5.0)')
        
        if not false_negatives.empty:
            # Save false negatives
            save_false_negatives(station_code, results_folder, false_negatives)
            print(f'  [INFO] Found {len(false_negatives)} false negatives (EQ M>=5.0 without anomaly)')
        
        results_summary[station_code] = {
            'anomalies_with_eq': len(correlations),
            'total_correlations': len(correlations),
            'false_negatives': len(false_negatives)
        }
    
    # Clean old earthquake stats files to ensure fresh calculation
    # SAVE TO ROOT for persistence
    web_data_dir = Path('.')
    old_stats_file = web_data_dir / 'today_earthquake_stats.json'
    old_recent_eq_file = web_data_dir / 'recent_earthquakes.csv'
    if old_stats_file.exists():
        old_stats_file.unlink()
        print(f'  [INFO] Deleted old earthquake stats file to ensure fresh calculation')
    if old_recent_eq_file.exists():
        old_recent_eq_file.unlink()
        print(f'  [INFO] Deleted old recent earthquakes file to ensure fresh calculation')
    
    # Get global earthquakes for last 7 days (for date-specific display)
    print(f'\n{"="*60}')
    print('Fetching global earthquakes (M>=5.0) for last 7 days...')
    from earthquake_integration import get_global_earthquakes_today, calculate_distance, fetch_usgs_earthquakes
    
    today = datetime.now().date()
    # SAVE TO ROOT for persistence
    web_data_dir = Path('.')
    
    # Process each of the last 7 days
    for days_back in range(7):
        target_date = today - timedelta(days=days_back)
        date_str = target_date.strftime('%Y-%m-%d')
        
        # Fetch earthquakes for this date
        start_date = datetime.combine(target_date, datetime.min.time())
        end_date = start_date + timedelta(days=1)
        
        print(f'  Fetching earthquakes for {date_str}...')
        day_eq = fetch_usgs_earthquakes(start_date, end_date, min_magnitude=5.0)
        
        if not day_eq.empty:
            print(f'    Found {len(day_eq)} earthquakes for {date_str}')
        else:
            print(f'    No earthquakes for {date_str}')
        
        # Calculate which earthquakes are within 200km of any station
        within_200km_count = 0
        if not day_eq.empty:
            stations_with_coords = []
            for station in stations_data:
                try:
                    lat = station.get('latitude')
                    lon = station.get('longitude')
                    if lat is not None and lon is not None:
                        lat = float(lat)
                        lon = float(lon)
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            stations_with_coords.append((lat, lon))
                except (ValueError, TypeError):
                    continue
            
            earthquakes_within_200km = set()
            for idx, eq in day_eq.iterrows():
                try:
                    eq_lat = eq.get('latitude')
                    eq_lon = eq.get('longitude')
                    
                    if pd.isna(eq_lat) or pd.isna(eq_lon):
                        continue
                    
                    eq_lat = float(eq_lat)
                    eq_lon = float(eq_lon)
                    
                    if not (-90 <= eq_lat <= 90 and -180 <= eq_lon <= 180):
                        continue
                    
                    for st_lat, st_lon in stations_with_coords:
                        try:
                            from earthquake_integration import calculate_distance
                            distance = calculate_distance(st_lat, st_lon, eq_lat, eq_lon)
                            if distance <= 200:
                                eq_id = eq.get('id', '')
                                if not eq_id or pd.isna(eq_id):
                                    eq_id = f"eq_{eq_lat:.3f}_{eq_lon:.3f}"
                                earthquakes_within_200km.add(str(eq_id))
                                break
                        except Exception:
                            continue
                except Exception:
                    continue
            
            within_200km_count = len(earthquakes_within_200km)
        
        # Save date-specific earthquake CSV
        eq_file = web_data_dir / f'recent_earthquakes_{date_str}.csv'
        if not day_eq.empty:
            day_eq.to_csv(eq_file, index=False)
        else:
            # Create empty CSV with headers
            empty_df = pd.DataFrame(columns=['time', 'latitude', 'longitude', 'magnitude', 'place', 'depth', 'type', 'id'])
            empty_df.to_csv(eq_file, index=False)
        
        # Save date-specific earthquake statistics
        eq_stats = {
            'analysis_date': date_str,
            'global_count': len(day_eq) if not day_eq.empty else 0,
            'within_200km_count': within_200km_count,
            'min_magnitude': 5.0
        }
        stats_file = web_data_dir / f'earthquake_stats_{date_str}.json'
        import json
        with open(stats_file, 'w') as f:
            json.dump(eq_stats, f, indent=2)
        
        if days_back == 0:
            # Also save as "today" for backward compatibility
            shutil.copy(eq_file, web_data_dir / 'recent_earthquakes.csv')
            shutil.copy(stats_file, web_data_dir / 'today_earthquake_stats.json')
            global_count = len(day_eq) if not day_eq.empty else 0
            recent_eq = day_eq.copy()
            within_200km_count = within_200km_count  # Use the value calculated above
    
    print(f'  [OK] Saved earthquake data for last 7 days')
    
    # Summary uses today's data (already calculated above)
    if not recent_eq.empty:
        # Get all station coordinates (ensure they're floats)
        stations_with_coords = []
        for station in stations_data:
            try:
                lat = station.get('latitude')
                lon = station.get('longitude')
                if lat is not None and lon is not None:
                    # Convert to float if needed
                    lat = float(lat)
                    lon = float(lon)
                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                        stations_with_coords.append((lat, lon))
            except (ValueError, TypeError):
                continue
        
        print(f'  [DEBUG] Checking {len(recent_eq)} earthquakes against {len(stations_with_coords)} stations')
        
        # Check each earthquake against all stations
        earthquakes_within_200km = set()
        for idx, eq in recent_eq.iterrows():
            try:
                eq_lat = eq.get('latitude')
                eq_lon = eq.get('longitude')
                
                # Convert to float and validate
                if pd.isna(eq_lat) or pd.isna(eq_lon):
                    continue
                
                eq_lat = float(eq_lat)
                eq_lon = float(eq_lon)
                
                if not (-90 <= eq_lat <= 90 and -180 <= eq_lon <= 180):
                    continue
                
                # Check if earthquake is within 200km of any station
                found_within_200km = False
                min_distance = float('inf')
                closest_station = None
                
                for st_lat, st_lon in stations_with_coords:
                    try:
                        distance = calculate_distance(st_lat, st_lon, eq_lat, eq_lon)
                        if distance < min_distance:
                            min_distance = distance
                            closest_station = (st_lat, st_lon)
                        
                        if distance <= 200:
                            found_within_200km = True
                            # Use earthquake ID if available, otherwise use coordinates
                            eq_id = eq.get('id', '')
                            if not eq_id or pd.isna(eq_id):
                                eq_id = f"eq_{eq_lat:.3f}_{eq_lon:.3f}"
                            earthquakes_within_200km.add(str(eq_id))
                            break  # Found one station, no need to check others
                    except Exception as e:
                        print(f'  [WARNING] Error calculating distance: {e}')
                        continue
                
                # Debug output for first few earthquakes
                if idx < 3:
                    place = eq.get('place', 'Unknown')
                    mag = eq.get('magnitude', 0)
                    if found_within_200km:
                        print(f'  [DEBUG] EQ at {place} (M{mag:.1f}) - WITHIN 200km (min distance: {min_distance:.1f}km)')
                    else:
                        print(f'  [DEBUG] EQ at {place} (M{mag:.1f}) - NOT within 200km (closest: {min_distance:.1f}km)')
                        
            except Exception as e:
                print(f'  [WARNING] Error processing earthquake: {e}')
                continue
        
        within_200km_count = len(earthquakes_within_200km)
    
    # Summary (already saved above in the loop, but print summary)
    print(f'  [INFO] Earthquakes (M>=5.0) globally today: {global_count}')
    print(f'  [INFO] Earthquakes (M>=5.0) within 200km of stations: {within_200km_count}')
    
    # Print summary
    print(f'\n{"="*60}')
    print('Summary:')
    print(f'{"="*60}')
    
    total_correlations = sum(r['total_correlations'] for r in results_summary.values())
    total_false_negatives = sum(r['false_negatives'] for r in results_summary.values())
    stations_with_correlations = sum(1 for r in results_summary.values() if r['total_correlations'] > 0)
    
    print(f'Total stations processed: {len(results_summary)}')
    print(f'Stations with correlations (M>=5.0): {stations_with_correlations}')
    print(f'Total reliable correlations (M>=5.0): {total_correlations}')
    print(f'Total false negatives (M>=5.0): {total_false_negatives}')
    
    # Show stations with correlations
    if stations_with_correlations > 0:
        print(f'\nStations with earthquake correlations (M>=5.0):')
        for station, data in results_summary.items():
            if data['total_correlations'] > 0:
                print(f'  {station}: {data["total_correlations"]} correlations')

if __name__ == '__main__':
    main()

```

---

## upload_results.py

```python
#!/usr/bin/env python3
"""
Prepare processed results for local web serving
Prepares files in web_output/ directory for Flask to serve
Handles date-specific files and 7-day data retention
"""

import os
import json
import re
import csv
from pathlib import Path
from datetime import datetime, timedelta
import shutil

# Configuration
OUTPUT_DIR = Path('web_output')  # Directory for prepared web files
ANOMALY_HISTORY_FILENAME = 'anomaly_history.json'
FALSE_NEGATIVE_HISTORY_FILENAME = 'false_negative_history.json'
HISTORY_SKIP_FILES = {
    'stations.json',
    ANOMALY_HISTORY_FILENAME,
    FALSE_NEGATIVE_HISTORY_FILENAME
}
RUN_ID = os.getenv('PRA_RUN_ID', 'manual')
HISTORY_DIR = Path('data') / 'history'
HISTORY_DIR.mkdir(parents=True, exist_ok=True)
ANOMALY_HISTORY_PATH = HISTORY_DIR / ANOMALY_HISTORY_FILENAME
FALSE_NEGATIVE_HISTORY_PATH = HISTORY_DIR / FALSE_NEGATIVE_HISTORY_FILENAME
RUN_REPORT_DIR = Path('data') / 'run_reports'
RUN_REPORT_SNAPSHOT = 'run_report_latest.json'

def parse_date_from_filename(filename):
    """Extract date from filename in format YYYY-MM-DD"""
    # Try to match date patterns like 2025-11-18 or 20251118
    date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
    if date_match:
        return date_match.group(0)
    date_match = re.search(r'(\d{4})(\d{2})(\d{2})', filename)
    if date_match:
        return f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
    return None

def get_available_dates():
    """Get list of available dates (last 7 days)"""
    dates = []
    today = datetime.now().date()
    for i in range(7):
        date = today - timedelta(days=i)
        dates.append(date.strftime('%Y-%m-%d'))
    return dates

def cleanup_old_files(data_dir, figures_dir, cutoff_date, skip_files=None):
    """Remove files older than cutoff_date"""
    deleted_count = 0
    skip_files = skip_files or set()
    
    # Clean JSON files in data/
    if data_dir.exists():
        for json_file in data_dir.glob('*.json'):
            if json_file.name in skip_files:
                continue
            if json_file.name != 'stations.json':
                file_date = parse_date_from_filename(json_file.name)
                if file_date:
                    try:
                        file_date_obj = datetime.strptime(file_date, '%Y-%m-%d').date()
                        if file_date_obj < cutoff_date:
                            json_file.unlink()
                            deleted_count += 1
                    except ValueError:
                        pass
    
    # Clean PNG files in figures/
    if figures_dir.exists():
        for png_file in figures_dir.rglob('*.png'):
            file_date = parse_date_from_filename(png_file.name)
            if file_date:
                try:
                    file_date_obj = datetime.strptime(file_date, '%Y-%m-%d').date()
                    if file_date_obj < cutoff_date:
                        png_file.unlink()
                        deleted_count += 1
                except ValueError:
                    pass
    
    return deleted_count

def load_history_entries(file_path):
    """Load history entries from a JSON file"""
    if file_path.exists():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get('entries'), list):
                    return data['entries']
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []

def save_history_entries(file_path, entries):
    """Persist history entries back to disk"""
    payload = {
        'last_updated': datetime.utcnow().isoformat(),
        'entries': entries
    }
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)

def safe_float(value):
    """Convert value to float if possible"""
    try:
        if value is None or value == '':
            return None
        return float(value)
    except (ValueError, TypeError):
        return None

def parse_any_date(value):
    """Parse a string into a date object (YYYY-MM-DD)"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        pass
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(str(value).split(' ')[0], fmt).date()
        except ValueError:
            continue
    return None


def normalize_date_string(value):
    """Convert various date strings to YYYY-MM-DD."""
    date = parse_any_date(value)
    if date:
        return date.strftime('%Y-%m-%d')
    return None


def build_run_report(stations, available_dates, anomaly_history, false_negative_history, data_dir):
    """Build and persist run report summarizing recent performance."""
    timestamp = datetime.utcnow().isoformat()
    latest_date = available_dates[0] if available_dates else None
    window_dates = set(available_dates or [])

    def in_window(value):
        if not window_dates:
            return False
        normalized = normalize_date_string(value)
        return normalized in window_dates

    anomalies_last_day = 0
    anomalies_last_week = 0
    correlated_last_week = 0
    for entry in anomaly_history:
        entry_date = normalize_date_string(entry.get('date'))
        if entry_date == latest_date:
            anomalies_last_day += 1
        if entry_date and entry_date in window_dates:
            anomalies_last_week += 1
            if entry.get('has_correlated_eq'):
                correlated_last_week += 1

    false_negatives_last_week = sum(
        1 for entry in false_negative_history
        if in_window(entry.get('earthquake_time') or entry.get('date'))
    )

    total_correlated = sum(1 for entry in anomaly_history if entry.get('has_correlated_eq'))
    total_false_positives = len(anomaly_history) - total_correlated

    recent_anomalies = [
        entry for entry in anomaly_history
        if in_window(entry.get('date'))
    ]
    recent_anomalies.sort(key=lambda e: e.get('date', ''), reverse=True)

    recent_false_negatives = [
        entry for entry in false_negative_history
        if in_window(entry.get('earthquake_time') or entry.get('date'))
    ]
    recent_false_negatives.sort(
        key=lambda e: (e.get('earthquake_time') or e.get('date') or ''),
        reverse=True
    )

    report = {
        'run_id': RUN_ID,
        'generated_at': timestamp,
        'latest_date': latest_date,
        'available_dates': available_dates,
        'stations_processed': len(stations),
        'metrics': {
            'anomalies_last_day': anomalies_last_day,
            'anomalies_last_7_days': anomalies_last_week,
            'correlated_last_7_days': correlated_last_week,
            'false_positives_last_7_days': anomalies_last_week - correlated_last_week,
            'false_negatives_last_7_days': false_negatives_last_week,
            'total_anomalies': len(anomaly_history),
            'total_correlated': total_correlated,
            'total_false_positives': total_false_positives,
            'total_false_negatives': len(false_negative_history),
        },
        'recent_anomalies': recent_anomalies[:50],
        'recent_false_negatives': recent_false_negatives[:50],
    }

    RUN_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RUN_REPORT_DIR / f'run_report_{RUN_ID}.json'
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    snapshot_path = RUN_REPORT_DIR / RUN_REPORT_SNAPSHOT
    with open(snapshot_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    # Copy snapshot into prepared data directory for frontend use
    shutil.copy(snapshot_path, data_dir / RUN_REPORT_SNAPSHOT)
    return report

def station_has_correlation(station_folder, target_date):
    """Check if a station has an earthquake correlation for a specific date"""
    if not target_date:
        return False
    csv_path = station_folder / 'earthquake_correlations.csv'
    if not csv_path.exists():
        return False
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                date_value = (
                    row.get('anomaly_date') or
                    row.get('anomaly_date ') or
                    row.get('anomaly_date'.upper()) or
                    row.get('anomalyDate')
                )
                anomaly_date = parse_any_date(date_value)
                if not anomaly_date:
                    continue
                if anomaly_date.strftime('%Y-%m-%d') != target_date:
                    continue
                magnitude = safe_float(row.get('earthquake_magnitude') or row.get('magnitude'))
                if magnitude is None:
                    magnitude = safe_float(row.get('earthquakeMag'))
                if magnitude is None or magnitude >= 5.0:
                    return True
    except Exception:
        return False
    return False

def update_anomaly_history(stations, data_dir, available_dates=None):
    """Append new anomalies to the persistent history log and retroactively link earthquakes
    
    This function:
    1. Keeps ALL anomalies ever detected (persistent history)
    2. Processes new anomalies from recent dates
    3. Retroactively links earthquakes that occurred 14-30 days AFTER anomalies
    
    Args:
        stations: List of station codes
        data_dir: Directory containing history files
        available_dates: List of recent dates to check for NEW anomalies
    """
    history_path = data_dir / ANOMALY_HISTORY_FILENAME
    entries = load_history_entries(history_path)
    entry_map = {}
    for entry in entries:
        station = entry.get('station')
        date = entry.get('date')
        if station and date:
            entry_map[f'{station}|{date}'] = entry
    updated = False
    now_iso = datetime.utcnow().isoformat()
    
    # Convert available_dates to set for faster lookup (only for NEW anomalies)
    date_filter = set(available_dates) if available_dates else None
    
    for station in stations:
        station_folder = Path('INTERMAGNET_DOWNLOADS') / station
        if not station_folder.exists():
            continue
        # CRITICAL FIX: Only process files for available dates
        if date_filter:
            # Only check files for specific dates
            json_files = []
            for date in date_filter:
                date_str = date.replace('-', '')
                pattern = f'PRA_Night_{station}_{date_str}.json'
                matching_files = list(station_folder.glob(pattern))
                json_files.extend(matching_files)
        else:
            # Fallback: process all files
            # CRITICAL FIX: Only process files for available dates
            if date_filter:
                # Only check files for specific dates
                json_files = []
                for date in date_filter:
                    date_str = date.replace('-', '')
                    pattern = f'PRA_Night_{station}_{date_str}.json'
                    matching_files = list(station_folder.glob(pattern))
                    json_files.extend(matching_files)
            else:
                # Fallback: process all files
                json_files = sorted(station_folder.glob('PRA_Night_*.json'))
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    station_data = json.load(f)
            except Exception:
                continue
            
            # Get the date first
            event_date = station_data.get('date') or parse_date_from_filename(json_file.name)
            if not event_date:
                continue
            
            # Only process NEW anomalies from recent dates
            # But keep all existing anomalies in history
            is_new_anomaly = date_filter and event_date in date_filter
            key = f'{station}|{event_date}'
            already_exists = key in entry_map
            
            # Skip if not a new anomaly and already exists
            if not is_new_anomaly and already_exists:
                continue
            
            is_anomalous = bool(station_data.get('is_anomalous') or station_data.get('isAnomalous'))
            n_hours = station_data.get('nAnomHours') or station_data.get('n_anom_hours') or 0
            
            # CRITICAL FIX: Skip if NOT anomalous OR if n_hours is 0
            # Must be anomalous AND have hours > 0 to be added
            if not is_anomalous or n_hours == 0:
                continue
            
            # Only process if it's a new anomaly from recent dates
            if not is_new_anomaly:
                continue
            
            entry = entry_map.get(key, {
                'station': station,
                'date': event_date,
                'first_detected': now_iso
            })
            entry['threshold'] = station_data.get('threshold')
            entry['n_anomaly_hours'] = n_hours
            entry['source_file'] = json_file.name
            entry['last_confirmed'] = now_iso
            
            # Check for earthquake correlation (14-30 days after anomaly)
            entry['has_correlated_eq'] = station_has_correlation(station_folder, event_date)
            
            entry_map[key] = entry
            updated = True
    
    # RETROACTIVE LINKING: Check all existing anomalies for new earthquakes
    # This handles cases where EQ occurs 14-30 days AFTER anomaly was detected
    print('[INFO] Checking for retroactive earthquake correlations...')
    retroactive_updates = 0
    for key, entry in entry_map.items():
        station = entry.get('station')
        event_date = entry.get('date')
        if not station or not event_date:
            continue
        
        station_folder = Path('INTERMAGNET_DOWNLOADS') / station
        if not station_folder.exists():
            continue
        
        # Re-check earthquake correlation (may have changed if new EQ occurred)
        old_status = entry.get('has_correlated_eq', False)
        new_status = station_has_correlation(station_folder, event_date)
        
        if old_status != new_status:
            entry['has_correlated_eq'] = new_status
            entry['last_confirmed'] = now_iso
            updated = True
            retroactive_updates += 1
    
    if retroactive_updates > 0:
        print(f'[INFO] Updated {retroactive_updates} anomalies with retroactive EQ correlations')
    
    if updated:
        sorted_entries = sorted(
            entry_map.values(),
            key=lambda e: (e.get('date', ''), e.get('station', ''))
        )
        save_history_entries(history_path, sorted_entries)
        
        # Count true positives and false positives
        true_positives = sum(1 for e in sorted_entries if e.get('has_correlated_eq'))
        false_positives = sum(1 for e in sorted_entries if not e.get('has_correlated_eq'))
        
        print(f'[INFO] Updated anomaly history: {len(sorted_entries)} total anomalies')
        print(f'[INFO]   True Positives: {true_positives} (with correlated EQ)')
        print(f'[INFO]   False Positives: {false_positives} (no correlated EQ)')
    else:
        # Ensure file exists even if no update occurred
        if not history_path.exists():
            sorted_entries = sorted(entries, key=lambda e: (e.get('date', ''), e.get('station', '')))
            save_history_entries(history_path, sorted_entries)
    entries = load_history_entries(history_path)
    # Persist to history directory for long-term aggregation
    if entries:
        save_history_entries(ANOMALY_HISTORY_PATH, entries)
    return entries

def update_false_negative_history(stations, data_dir):
    """Ensure false negative history stays cumulative"""
    history_path = data_dir / FALSE_NEGATIVE_HISTORY_FILENAME
    entries = load_history_entries(history_path)
    entry_map = {}
    for entry in entries:
        station = entry.get('station')
        eq_time = entry.get('earthquake_time')
        if station and eq_time:
            entry_map[f'{station}|{eq_time}'] = entry
    updated = False
    now_iso = datetime.utcnow().isoformat()
    for station in stations:
        station_folder = Path('INTERMAGNET_DOWNLOADS') / station
        csv_path = station_folder / 'false_negatives.csv'
        if not csv_path.exists():
            continue
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    eq_time = row.get('earthquake_time') or row.get('time')
                    if not eq_time:
                        continue
                    key = f'{station}|{eq_time}'
                    entry = entry_map.get(key, {
                        'station': station,
                        'earthquake_time': eq_time,
                        'first_logged': now_iso
                    })
                    entry['earthquake_magnitude'] = safe_float(row.get('earthquake_magnitude') or row.get('magnitude'))
                    entry['earthquake_distance_km'] = safe_float(row.get('earthquake_distance_km') or row.get('distance_km'))
                    entry['earthquake_place'] = row.get('earthquake_place') or row.get('place')
                    entry['earthquake_latitude'] = safe_float(row.get('earthquake_latitude') or row.get('latitude'))
                    entry['earthquake_longitude'] = safe_float(row.get('earthquake_longitude') or row.get('longitude'))
                    entry['last_confirmed'] = now_iso
                    entry['source_file'] = csv_path.name
                    entry_map[key] = entry
                    updated = True
        except Exception:
            continue
    if updated:
        sorted_entries = sorted(
            entry_map.values(),
            key=lambda e: (e.get('earthquake_time', ''), e.get('station', ''))
        )
        save_history_entries(history_path, sorted_entries)
        print(f'[INFO] Updated false negative history with {len(sorted_entries)} total entries')
    else:
        if not history_path.exists():
            save_history_entries(history_path, entries)
    entries = load_history_entries(history_path)
    if entries:
        save_history_entries(FALSE_NEGATIVE_HISTORY_PATH, entries)
    return entries

def get_stations():
    """Get list of stations - auto-detect from processed data or use env var"""
    stations_env = os.getenv('INTERMAGNET_STATIONS', '')
    if stations_env:
        return [s.strip() for s in stations_env.split(',')]
    
    # Auto-detect: Find all stations that have been processed
    downloads_dir = Path('INTERMAGNET_DOWNLOADS')
    if downloads_dir.exists():
        stations = []
        for station_dir in downloads_dir.iterdir():
            if station_dir.is_dir() and not station_dir.name.startswith('.'):
                # Check if this station has processed JSON files
                json_files = list(station_dir.glob('PRA_Night_*.json'))
                if json_files:
                    stations.append(station_dir.name)
        
        if stations:
            stations.sort()
            print(f'[INFO] Auto-detected {len(stations)} processed stations')
            return stations
    
    # Fallback: Try to load from stations.json
    if Path('stations.json').exists():
        try:
            with open('stations.json', 'r') as f:
                data = json.load(f)
                if isinstance(data, dict) and 'stations' in data:
                    if isinstance(data['stations'], list):
                        return data['stations']
                    elif isinstance(data['stations'], dict):
                        return list(data['stations'].keys())
        except Exception:
            pass
    
    # Last resort: raise error
    raise ValueError("No stations found. Please ensure data has been processed.")

def generate_aggregated_data_files(stations, available_dates, data_dir):
    """Generate aggregated JSON files per date for faster frontend loading
    
    Creates a single JSON file per date containing all station data, earthquake correlations,
    and metadata. This reduces frontend network requests from 100+ to 1 per date.
    
    Args:
        stations: List of station codes
        available_dates: List of dates to generate aggregated files for
        data_dir: Directory containing individual station JSON files
    
    Returns:
        Number of aggregated files generated
    """
    print('[INFO] Generating aggregated data files...')
    generated_count = 0
    
    # Load station metadata once
    metadata_dict = {}
    if Path('stations.json').exists():
        try:
            with open('stations.json', 'r', encoding='utf-8') as f:
                stations_metadata = json.load(f)
                
            # Handle different formats of stations.json
            if isinstance(stations_metadata, dict):
                if 'stations' in stations_metadata:
                    if isinstance(stations_metadata['stations'], list):
                        for station_obj in stations_metadata['stations']:
                            if isinstance(station_obj, dict) and 'code' in station_obj:
                                code = station_obj['code']
                                metadata_dict[code] = {
                                    'name': station_obj.get('name', ''),
                                    'country': station_obj.get('country', ''),
                                    'latitude': station_obj.get('latitude', 0),
                                    'longitude': station_obj.get('longitude', 0),
                                    'timezone': station_obj.get('timezone', '')
                                }
                    elif isinstance(stations_metadata['stations'], dict):
                        metadata_dict = stations_metadata['stations']
                elif 'metadata' in stations_metadata and isinstance(stations_metadata['metadata'], list):
                    for station_obj in stations_metadata['metadata']:
                        if isinstance(station_obj, dict) and 'code' in station_obj:
                            code = station_obj['code']
                            metadata_dict[code] = {
                                'name': station_obj.get('name', ''),
                                'country': station_obj.get('country', ''),
                                'latitude': station_obj.get('latitude', 0),
                                'longitude': station_obj.get('longitude', 0),
                                'timezone': station_obj.get('timezone', '')
                            }
        except Exception as e:
            print(f'[WARNING] Could not load station metadata: {e}')
    
    # Generate aggregated file for each date
    for date in available_dates:
        aggregated_data = {
            'date': date,
            'generated_at': datetime.utcnow().isoformat(),
            'stations': {},
            'earthquake_correlations': {},
            'false_negatives': {},
            'metadata': metadata_dict
        }
        
        stations_with_data = 0
        
        # Collect data for each station
        for station in stations:
            # Try to load station JSON for this date
            station_json = data_dir / f'{station}_{date}.json'
            
            # FALLBACK LOGIC: If data for this date doesn't exist, try previous day
            # This ensures that "Today's" map isn't empty just because data hasn't arrived yet
            if not station_json.exists():
                try:
                    current_date_obj = datetime.strptime(date, '%Y-%m-%d').date()
                    prev_date_obj = current_date_obj - timedelta(days=1)
                    prev_date = prev_date_obj.strftime('%Y-%m-%d')
                    prev_station_json = data_dir / f'{station}_{prev_date}.json'
                    
                    if prev_station_json.exists():
                        # print(f'[INFO] Using fallback data for {station}: {prev_date} instead of {date}')
                        station_json = prev_station_json
                except ValueError:
                    pass

            if station_json.exists():
                try:
                    with open(station_json, 'r', encoding='utf-8') as f:
                        station_data = json.load(f)
                    aggregated_data['stations'][station] = station_data
                    stations_with_data += 1
                except Exception as e:
                    print(f'[WARNING] Could not load {station_json.name}: {e}')
            
            # Load earthquake correlations CSV
            # Use same fallback logic for correlations
            eq_corr_csv = data_dir / f'{station}_earthquake_correlations.csv' # Start with static file
            
            # Try date specific first (or fallback)
            eq_date_file = data_dir / f'{station}_{date}_earthquake_correlations.json'
            if not eq_date_file.exists():
                 try:
                    current_date_obj = datetime.strptime(date, '%Y-%m-%d').date()
                    prev_date_obj = current_date_obj - timedelta(days=1)
                    prev_date = prev_date_obj.strftime('%Y-%m-%d')
                    prev_eq_file = data_dir / f'{station}_{prev_date}_earthquake_correlations.json'
                    if prev_eq_file.exists():
                        eq_date_file = prev_eq_file
                 except:
                     pass
            
            # Load correlations... (existing logic modified to use eq_date_file if it exists?)
            # Actually, standard logic loads from CSV or parses date from big CSV. 
            # The original code parses a monolithic CSV `station_earthquake_correlations.csv`.
            # Let's keep the existing CSV logic for simplicity as it filters by date anyway.
            # But if there are individual JSONs (not standard in this repo?), we might use them.
            # The current code only loads `station_earthquake_correlations.csv` and filters rows.
            # Since that CSV contains ALL history, we don't need fallback for it.
            
            if eq_corr_csv.exists():
                try:
                    with open(eq_corr_csv, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        correlations = []
                        for row in reader:
                            # Filter by date and magnitude >= 5.0
                            anomaly_date = parse_any_date(
                                row.get('anomaly_date') or 
                                row.get('anomaly_date ') or 
                                row.get('anomalyDate')
                            )
                            # Logic to match date OR match fallback date?
                            # If we are displaying 'Today' map but showing 'Yesterday' station data,
                            # we should probably show 'Yesterday' correlations for that station?
                            # For now, let's strictly show correlations for the AGGREGATED DATE to avoid confusion.
                            # If the user sees "Today", they expect "Today's" events.
                            # Mixing dates in correlations might be confusing. 
                            # But if the station data IS from yesterday, matching anomalies from yesterday makes sense.
                            # Let's Stick to STRICT date matching for now for correlations to avoid misleading data.
                            
                            if anomaly_date and anomaly_date.strftime('%Y-%m-%d') == date:
                                magnitude = safe_float(row.get('earthquake_magnitude') or row.get('magnitude'))
                                if magnitude is None or magnitude >= 5.0:
                                    correlations.append(dict(row))
                        
                        if correlations:
                            aggregated_data['earthquake_correlations'][station] = correlations
                except Exception as e:
                    print(f'[WARNING] Could not load {eq_corr_csv.name}: {e}')
            
            # Load false negatives CSV
            fn_csv = data_dir / f'{station}_false_negatives.csv'
            if fn_csv.exists():
                try:
                    with open(fn_csv, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        false_negs = [dict(row) for row in reader]
                        if false_negs:
                            aggregated_data['false_negatives'][station] = false_negs
                except Exception as e:
                    print(f'[WARNING] Could not load {fn_csv.name}: {e}')
        
        # Only save if we have data for at least one station
        if stations_with_data > 0:
            output_file = data_dir / f'aggregated_{date}.json'
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(aggregated_data, f, indent=2)
            
            file_size_kb = output_file.stat().st_size / 1024
            print(f'[INFO] Generated {output_file.name} ({stations_with_data} stations, {file_size_kb:.1f} KB)')
            generated_count += 1
        else:
            print(f'[WARNING] No data found for date {date}, skipping aggregated file')
    
    print(f'[INFO] Generated {generated_count} aggregated data files')
    return generated_count

def prepare_web_output():
    """Prepare static files for web deployment with date-specific handling"""
    print('Preparing web output...')
    
    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Copy static frontend files
    static_dir = OUTPUT_DIR / 'static'
    static_dir.mkdir(exist_ok=True)
    
    # Copy CSS
    if Path('static/style.css').exists():
        shutil.copy('static/style.css', static_dir / 'style.css')
    
    # Copy JS
    if Path('static/app.js').exists():
        shutil.copy('static/app.js', static_dir / 'app.js')
    
    # Create data and figures directories
    data_dir = OUTPUT_DIR / 'data'
    data_dir.mkdir(exist_ok=True)
    
    figures_dir = OUTPUT_DIR / 'figures'
    figures_dir.mkdir(exist_ok=True)
    
    # Get available dates (last 7 days)
    available_dates = get_available_dates()
    most_recent_date = available_dates[0] if available_dates else None
    
    print(f'[INFO] Available dates: {", ".join(available_dates)}')
    print(f'[INFO] Most recent date: {most_recent_date}')
    
    # Get stations
    stations = get_stations()
    
    # Copy date-specific files for the last 7 days
    cutoff_date = (datetime.now() - timedelta(days=6)).date()
    
    for station in stations:
        station_folder = Path('INTERMAGNET_DOWNLOADS') / station
        
        if not station_folder.exists():
            continue
        
        # Copy date-specific JSON files
        # Note: JSON files are named with "today's" date but contain data from yesterday 20:00 to today 04:00
        # So we need to create copies for both today and yesterday
        json_files = list(station_folder.glob('PRA_Night_*.json'))
        for json_file in json_files:
            file_date = parse_date_from_filename(json_file.name)
            if file_date:
                try:
                    file_date_obj = datetime.strptime(file_date, '%Y-%m-%d').date()
                    if file_date_obj >= cutoff_date:
                        # Copy as {station}_{date}.json (always copy if within date range, not just if in available_dates)
                        # This ensures files are available even if they're not in the standard 7-day window
                        dest_file = data_dir / f'{station}_{file_date}.json'
                        shutil.copy(json_file, dest_file)
                        print(f'[INFO] Copied {station}_{file_date}.json')
                        
                        # Also create a copy for yesterday (since the JSON contains yesterday 20:00 to today 04:00)
                        yesterday_date_obj = file_date_obj - timedelta(days=1)
                        yesterday_date = yesterday_date_obj.strftime('%Y-%m-%d')
                        if yesterday_date_obj >= cutoff_date:  # Only if yesterday is also within range
                            dest_file_yesterday = data_dir / f'{station}_{yesterday_date}.json'
                            # Always copy/overwrite to ensure we have the latest data
                            shutil.copy(json_file, dest_file_yesterday)
                            print(f'[INFO] Created {station}_{yesterday_date}.json (from {file_date} data)')
                except ValueError:
                    pass
        
        # Copy date-specific figures
        station_figures_dir = station_folder / 'figures'
        if station_figures_dir.exists():
            web_station_figures_dir = figures_dir / station
            web_station_figures_dir.mkdir(exist_ok=True)
            
            for fig_file in station_figures_dir.glob('*.png'):
                file_date = parse_date_from_filename(fig_file.name)
                if file_date and file_date in available_dates:
                    try:
                        file_date_obj = datetime.strptime(file_date, '%Y-%m-%d').date()
                        if file_date_obj >= cutoff_date:
                            shutil.copy(fig_file, web_station_figures_dir / fig_file.name)
                    except ValueError:
                        pass

        # Copy supporting CSVs (earthquake correlations, false negatives)
        eq_corr_path = station_folder / 'earthquake_correlations.csv'
        if eq_corr_path.exists():
            shutil.copy(eq_corr_path, data_dir / f'{station}_earthquake_correlations.csv')
        fn_path = station_folder / 'false_negatives.csv'
        if fn_path.exists():
            shutil.copy(fn_path, data_dir / f'{station}_false_negatives.csv')
    
    # Copy date-specific earthquake files
    for date in available_dates:
        eq_csv = Path(f'recent_earthquakes_{date}.csv')
        if eq_csv.exists():
            shutil.copy(eq_csv, data_dir / eq_csv.name)
            try:
                os.remove(eq_csv) # Clean up from root
                print(f'[INFO] Moved/Cleaned up root file: {eq_csv.name}')
            except Exception as e:
                print(f'[WARNING] Failed to delete root file {eq_csv.name}: {e}')
            
        # Copy date-specific earthquake stats (for summary boxes)
        eq_stats = Path(f'earthquake_stats_{date}.json')
        if eq_stats.exists():
            shutil.copy(eq_stats, data_dir / eq_stats.name)
            try:
                os.remove(eq_stats) # Clean up from root
                print(f'[INFO] Moved/Cleaned up root file: {eq_stats.name}')
            except Exception as e:
                print(f'[WARNING] Failed to delete root file {eq_stats.name}: {e}')
    
    # Clean up old files (older than 6 days)
    deleted = cleanup_old_files(data_dir, figures_dir, cutoff_date, skip_files=HISTORY_SKIP_FILES)
    if deleted > 0:
        print(f'[INFO] Cleaned up {deleted} old files')

    # Keep cumulative anomaly and false negative histories
    anomaly_history = update_anomaly_history(stations, data_dir, available_dates)
    false_negative_history = update_false_negative_history(stations, data_dir)
    run_report = build_run_report(stations, available_dates, anomaly_history, false_negative_history, data_dir)
    
    # Generate aggregated data files for faster frontend loading
    # This combines all station data per date into single JSON files
    generate_aggregated_data_files(stations, available_dates, data_dir)
    
    # Load station metadata from root stations.json
    metadata_dict = {}
    if Path('stations.json').exists():
        try:
            with open('stations.json', 'r', encoding='utf-8') as f:
                stations_metadata = json.load(f)
                
            # Handle different formats of stations.json
            if isinstance(stations_metadata, dict):
                if 'stations' in stations_metadata:
                    # Format 1: {"stations": [{"code": "KAK", "name": "...", ...}, ...]}
                    if isinstance(stations_metadata['stations'], list):
                        for station_obj in stations_metadata['stations']:
                            if isinstance(station_obj, dict) and 'code' in station_obj:
                                code = station_obj['code']
                                metadata_dict[code] = {
                                    'name': station_obj.get('name', ''),
                                    'country': station_obj.get('country', ''),
                                    'latitude': station_obj.get('latitude', 0),
                                    'longitude': station_obj.get('longitude', 0),
                                    'timezone': station_obj.get('timezone', '')
                                }
                        if metadata_dict:
                            print(f'[INFO] Loaded metadata for {len(metadata_dict)} stations from root stations.json')
                    # Format 2: {"stations": {"KAK": {...}, ...}}
                    elif isinstance(stations_metadata['stations'], dict):
                        metadata_dict = stations_metadata['stations']
                        print(f'[INFO] Loaded metadata for {len(metadata_dict)} stations from root stations.json (dict format)')
                # Format 3: {"metadata": [...]} - array of metadata objects
                elif 'metadata' in stations_metadata and isinstance(stations_metadata['metadata'], list):
                    for station_obj in stations_metadata['metadata']:
                        if isinstance(station_obj, dict) and 'code' in station_obj:
                            code = station_obj['code']
                            metadata_dict[code] = {
                                'name': station_obj.get('name', ''),
                                'country': station_obj.get('country', ''),
                                'latitude': station_obj.get('latitude', 0),
                                'longitude': station_obj.get('longitude', 0),
                                'timezone': station_obj.get('timezone', '')
                            }
                    if metadata_dict:
                        print(f'[INFO] Loaded metadata for {len(metadata_dict)} stations from metadata array')
        except Exception as e:
            print(f'[WARNING] Could not load station metadata: {e}')
            import traceback
            traceback.print_exc()
    
    # Create stations.json with available dates and metadata
    stations_json = {
        'stations': stations,
        'available_dates': available_dates,
        'most_recent_date': most_recent_date,
        'last_updated': datetime.now().isoformat(),
    }
    
    # Add station metadata - ensure all stations have at least empty metadata
    if metadata_dict:
        print(f'[INFO] Using metadata for {len(metadata_dict)} stations')
        # Only include metadata for stations that are actually processed
        filtered_metadata = {code: metadata_dict[code] for code in stations if code in metadata_dict}
        stations_json['metadata'] = filtered_metadata
        # Add empty metadata for stations without metadata
        for station in stations:
            if station not in stations_json['metadata']:
                stations_json['metadata'][station] = {}
        print(f'[INFO] Final metadata contains {len(stations_json["metadata"])} stations')
    else:
        print(f'[WARNING] No metadata found, creating empty metadata for {len(stations)} stations')
        # If no metadata found, create empty dict for all stations
        stations_json['metadata'] = {s: {} for s in stations}
    
    with open(data_dir / 'stations.json', 'w') as f:
        json.dump(stations_json, f, indent=2)
    
    # Copy index.html directly from template
    template_path = Path('templates/index.html')
    if template_path.exists():
        shutil.copy(template_path, OUTPUT_DIR / 'index.html')
        print('[OK] Copied index.html from template')
    else:
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    print(f'[OK] Web output prepared in {OUTPUT_DIR}')
    return OUTPUT_DIR, anomaly_history, false_negative_history, run_report

def main():
    """Main function - prepare files for local serving"""
    print('='*60)
    print('PRA Results Preparation Script')
    print('='*60)
    
    # Prepare web output
    output_dir, anomaly_history, false_negative_history, run_report = prepare_web_output()

    
    print('\n[OK] Files prepared successfully!')
    print(f'\nOutput directory: {output_dir.absolute()}')
    print('\nTo view the dashboard:')
    print('   python app.py')
    print('   Then open: http://localhost:5000')
    print('\nThe Flask app will serve files directly from:')
    print('   - web_output/ (prepared files)')
    print('   - INTERMAGNET_DOWNLOADS/ (source data)')
    
    return 0

if __name__ == '__main__':
    exit(main())
```

---

## app.py

```python
#!/usr/bin/env python3
"""
Flask web application for PRA Nighttime Detection
Local testing interface
"""

from flask import Flask, render_template, jsonify, send_from_directory
from pathlib import Path
import json
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
import os

app = Flask(__name__)

# Serve static files from web_output/static
@app.route('/static/<path:filename>')
def serve_static(filename):
    # Try web_output first
    web_static = Path('web_output') / 'static' / filename
    if web_static.exists():
        return send_from_directory('web_output/static', filename)
    # Fallback to source static
    return send_from_directory('static', filename)

# Serve data files from web_output/data
@app.route('/data/<path:filename>')
def serve_data_file(filename):
    """Serve data files - tries web_output first, then source directories"""
    # Try web_output first (prepared files)
    web_data = Path('web_output') / 'data' / filename
    if web_data.exists():
        return send_from_directory('web_output/data', filename)
    
    # Fallback: serve directly from source directories
    data_folder = Path('INTERMAGNET_DOWNLOADS')
    
    # Handle stations.json (metadata)
    if filename == 'stations.json':
        stations_json = Path('stations.json')
        if stations_json.exists():
            return send_from_directory('.', 'stations.json')
    
    # Handle station-specific files
    if filename.endswith('_latest.json'):
        station = filename.replace('_latest.json', '')
        json_file = data_folder / station / f'PRA_Night_{station}_*.json'
        import glob
        files = glob.glob(str(json_file))
        if files:
            latest = max(files, key=lambda p: Path(p).stat().st_mtime)
            return send_from_directory(str(Path(latest).parent), Path(latest).name)
    elif filename.endswith('_anomalies.csv'):
        station = filename.replace('_anomalies.csv', '')
        anomaly_file = data_folder / station / 'anomaly_master_table.csv'
        if anomaly_file.exists():
            return send_from_directory(str(anomaly_file.parent), 'anomaly_master_table.csv')
    elif filename.endswith('_earthquake_correlations.csv'):
        station = filename.replace('_earthquake_correlations.csv', '')
        eq_file = data_folder / station / 'earthquake_correlations.csv'
        if eq_file.exists():
            return send_from_directory(str(eq_file.parent), 'earthquake_correlations.csv')
    
    return "Data not found", 404

# Serve figures from web_output/figures
@app.route('/figures/<path:filename>')
def serve_figure_file(filename):
    """Serve figure files"""
    # Try web_output first (for static deployment)
    web_fig = Path('web_output') / 'figures' / filename
    if web_fig.exists():
        return send_from_directory('web_output/figures', filename)
    
    # Fallback to local folder
    fig_folder = Path('INTERMAGNET_DOWNLOADS')
    parts = filename.split('/')
    if len(parts) == 2:
        station, fig_name = parts
        fig_file = fig_folder / station / 'figures' / fig_name
        if fig_file.exists():
            return send_from_directory(str(fig_file.parent), fig_name)
    
    return "Figure not found", 404

TZ = ZoneInfo('Asia/Tokyo')
RUN_TIMEZONE = ZoneInfo('Asia/Singapore')

def get_stations():
    """Get list of stations"""
    stations_env = os.getenv('INTERMAGNET_STATIONS', '')
    if stations_env:
        return [s.strip() for s in stations_env.split(',')]
    return ['KAK']

def get_latest_results(station_code):
    """Get latest results for a station"""
    data_folder = Path('INTERMAGNET_DOWNLOADS') / station_code
    
    # Find latest JSON file
    json_files = list(data_folder.glob('PRA_Night_*.json'))
    if not json_files:
        return None
    
    latest_file = max(json_files, key=lambda p: p.stat().st_mtime)
    
    with open(latest_file, 'r') as f:
        return json.load(f)

def get_anomaly_table(station_code):
    """Get anomaly master table"""
    log_file = Path('INTERMAGNET_DOWNLOADS') / station_code / 'anomaly_master_table.csv'
    if not log_file.exists():
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(log_file)
        # Sort by date (most recent first)
        if 'Range' in df.columns:
            df['_sort_date'] = df['Range'].str.split().str[0]
            df = df.sort_values('_sort_date', ascending=False, na_position='last')
            df = df.drop('_sort_date', axis=1)
        return df.head(10)  # Last 10 anomalies
    except:
        return pd.DataFrame()

def get_figures(station_code, limit=5):
    """Get list of recent figures"""
    fig_folder = Path('INTERMAGNET_DOWNLOADS') / station_code / 'figures'
    if not fig_folder.exists():
        return []
    
    figures = list(fig_folder.glob('PRA_*.png'))
    figures.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [f.name for f in figures[:limit]]

@app.route('/')
def index():
    """Main page - serve static HTML from web_output"""
    # Serve from web_output if it exists (prepared by upload_results.py)
    static_index = Path('web_output') / 'index.html'
    if static_index.exists():
        return send_from_directory('web_output', 'index.html')
    
    # If web_output doesn't exist, prepare it automatically
    print('[INFO] web_output/ not found, preparing files...')
    try:
        from upload_results import prepare_web_output
        prepare_web_output()
        if static_index.exists():
            return send_from_directory('web_output', 'index.html')
    except Exception as e:
        print(f'[WARNING] Could not prepare web_output: {e}')
    
    # Final fallback: use template (if exists)
    stations = get_stations()
    station_data = {}
    
    for station in stations:
        results = get_latest_results(station)
        anomalies = get_anomaly_table(station)
        figures = get_figures(station)
        
        station_data[station] = {
            'results': results,
            'anomalies': anomalies.to_dict('records') if not anomalies.empty else [],
            'figures': figures,
            'has_data': results is not None
        }
    
    return render_template('index.html', stations=stations, station_data=station_data)

@app.route('/api/stations')
def api_stations():
    """API: Get list of stations"""
    return jsonify(get_stations())

@app.route('/api/results/<station_code>')
def api_results(station_code):
    """API: Get latest results for a station"""
    results = get_latest_results(station_code)
    if results:
        return jsonify(results)
    return jsonify({'error': 'No results found'}), 404

@app.route('/api/anomalies/<station_code>')
def api_anomalies(station_code):
    """API: Get anomalies for a station"""
    anomalies = get_anomaly_table(station_code)
    if not anomalies.empty:
        return jsonify(anomalies.to_dict('records'))
    return jsonify([])

@app.route('/figures/<station_code>/<filename>')
def serve_figure(station_code, filename):
    """Serve figure files"""
    # Try web_output first (for static deployment)
    web_fig = Path('web_output') / 'figures' / station_code / filename
    if web_fig.exists():
        return send_from_directory(str(web_fig.parent), filename)
    
    # Fallback to local folder
    fig_folder = Path('INTERMAGNET_DOWNLOADS') / station_code / 'figures'
    if fig_folder.exists():
        return send_from_directory(str(fig_folder), filename)
    
    return "Figure not found", 404

@app.route('/data/<filename>')
def serve_data(filename):
    """Serve data files - tries web_output first, then source directories"""
    # Try web_output first (prepared files)
    web_data = Path('web_output') / 'data' / filename
    if web_data.exists():
        return send_from_directory(str(web_data.parent), filename)
    
    # Fallback: serve directly from source directories
    data_folder = Path('INTERMAGNET_DOWNLOADS')
    
    # Handle stations.json (metadata)
    if filename == 'stations.json':
        stations_json = Path('stations.json')
        if stations_json.exists():
            return send_from_directory('.', 'stations.json')
    
    # Handle station-specific files
    if filename.endswith('_latest.json'):
        station = filename.replace('_latest.json', '')
        json_file = data_folder / station / f'PRA_Night_{station}_*.json'
        import glob
        files = glob.glob(str(json_file))
        if files:
            latest = max(files, key=lambda p: Path(p).stat().st_mtime)
            return send_from_directory(str(Path(latest).parent), Path(latest).name)
    elif filename.endswith('_anomalies.csv'):
        station = filename.replace('_anomalies.csv', '')
        anomaly_file = data_folder / station / 'anomaly_master_table.csv'
        if anomaly_file.exists():
            return send_from_directory(str(anomaly_file.parent), 'anomaly_master_table.csv')
    elif filename.endswith('_earthquake_correlations.csv'):
        station = filename.replace('_earthquake_correlations.csv', '')
        eq_file = data_folder / station / 'earthquake_correlations.csv'
        if eq_file.exists():
            return send_from_directory(str(eq_file.parent), 'earthquake_correlations.csv')
    
    return "Data not found", 404

if __name__ == '__main__':
    # Create necessary directories
    Path('templates').mkdir(exist_ok=True)
    Path('static').mkdir(exist_ok=True)
    Path('web_output').mkdir(exist_ok=True)
    
    print('='*60)
    print('PRA Nighttime Detection - Local Web Server')
    print('='*60)
    print('\nStarting Flask server...')
    print('Dashboard will be available at: http://localhost:5000')
    print('\nTip: Run "python upload_results.py" first to prepare files')
    print('   (or Flask will prepare them automatically on first load)')
    print('='*60)
    print()
    
    app.run(debug=True, host='0.0.0.0', port=5000)

```

---

## ensure_station_data.py

```python
#!/usr/bin/env python3
"""
Ensure latest INTERMAGNET data files exist before running the full workflow.

This script checks each station's local time. If the nighttime window (20:00-04:00)
has not yet completed, it ensures yesterday's data is downloaded. Once the window
has passed, it also verifies today's data so processing can proceed immediately.
"""

from datetime import datetime, timedelta
from pathlib import Path

from load_stations import load_stations
from pra_nighttime import (
    get_station_timezone,
    get_data_folder,
    download_data,
)


def ensure_station_files():
    stations = load_stations()
    if not stations:
        print('[WARNING] No stations found during preflight data check.')
        return 0

    total_downloads = 0

    for station in stations:
        code = station.get('code') if isinstance(station, dict) else station
        if not code:
            continue

        station_tz = get_station_timezone(code)
        now_local = datetime.now(station_tz)
        today_local = now_local.date()
        yesterday_local = today_local - timedelta(days=1)

        # Always ensure yesterday's data exists (used for fallback if today isn't ready)
        dates_to_check = {yesterday_local}

        if now_local.hour >= 4:
            # After 04:00 local time, the nighttime window has completed.
            dates_to_check.add(today_local)
        else:
            # Before 04:00, ensure two days ago is available to prevent stale displays.
            dates_to_check.add(today_local - timedelta(days=2))

        data_folder = get_data_folder(code)
        data_folder.mkdir(parents=True, exist_ok=True)

        for date_obj in dates_to_check:
            if not date_obj:
                continue
            # Do not request future dates
            if date_obj > today_local:
                continue

            # OPTIMIZATION: Check if PRA output already exists for this date
            # If PRA analysis has been run and output exists, skip downloading raw data
            pra_output_file = Path(f'results/{code}_{date_obj.strftime("%Y%m%d")}.json')
            if pra_output_file.exists() and pra_output_file.stat().st_size > 0:
                # PRA output exists, no need to download raw data
                continue

            target_dt = datetime.combine(date_obj, datetime.min.time()).replace(tzinfo=station_tz)
            filename = f'{code}_{date_obj.strftime("%Y%m%d")}.iaga2002'
            data_path = data_folder / filename
            
            # Check if raw data file already exists
            if data_path.exists() and data_path.stat().st_size > 0:
                continue

            # Only download if neither PRA output nor raw data exists
            result = download_data(code, target_dt, data_folder)
            if result and result.exists():
                total_downloads += 1
                print(f'[OK] Downloaded {code} data for {date_obj}')
            else:
                print(f'[WARN] Could not download {code} data for {date_obj}')

    print(f'[INFO] Preflight data check complete. New files downloaded: {total_downloads}')
    return 0


if __name__ == '__main__':
    exit(ensure_station_files())

```

---

## load_stations.py

```python
#!/usr/bin/env python3
"""
Utility to load and validate INTERMAGNET station codes
"""

import json
from pathlib import Path

STATIONS_FILE = Path('stations.json')

def load_stations():
    """Load station codes from JSON file"""
    if not STATIONS_FILE.exists():
        print(f'Warning: {STATIONS_FILE} not found')
        return []
    
    with open(STATIONS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        return data.get('stations', [])

def get_station_info(code):
    """Get information for a specific station code"""
    stations = load_stations()
    for station in stations:
        if station['code'].upper() == code.upper():
            return station
    return None

def validate_station_codes(codes):
    """Validate a list of station codes"""
    stations = load_stations()
    valid_codes = {s['code'].upper() for s in stations}
    
    valid = []
    invalid = []
    
    for code in codes:
        code_upper = code.strip().upper()
        if code_upper in valid_codes:
            valid.append(code_upper)
        else:
            invalid.append(code)
    
    return valid, invalid

def list_all_stations():
    """List all available station codes"""
    stations = load_stations()
    print(f'\nAvailable INTERMAGNET Stations ({len(stations)} total):\n')
    print('Code | Name                    | Country')
    print('-' * 60)
    
    for station in sorted(stations, key=lambda x: x['code']):
        print(f"{station['code']:4s} | {station['name']:22s} | {station['country']}")
    
    print(f'\nTotal: {len(stations)} stations')
    return stations

def get_stations_by_country():
    """Group stations by country"""
    stations = load_stations()
    by_country = {}
    
    for station in stations:
        country = station['country']
        if country not in by_country:
            by_country[country] = []
        by_country[country].append(station)
    
    return by_country

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'list':
            list_all_stations()
        elif command == 'validate':
            if len(sys.argv) > 2:
                codes = sys.argv[2].split(',')
                valid, invalid = validate_station_codes(codes)
                print(f'\nValid codes: {", ".join(valid)}')
                if invalid:
                    print(f'Invalid codes: {", ".join(invalid)}')
            else:
                print('Usage: python load_stations.py validate KAK,HER,NGK')
        elif command == 'info':
            if len(sys.argv) > 2:
                code = sys.argv[2]
                info = get_station_info(code)
                if info:
                    print(f'\nStation: {info["code"]}')
                    print(f'Name: {info["name"]}')
                    print(f'Country: {info["country"]}')
                    print(f'Coordinates: {info["latitude"]}, {info["longitude"]}')
                    print(f'Timezone: {info["timezone"]}')
                else:
                    print(f'Station code "{code}" not found')
            else:
                print('Usage: python load_stations.py info KAK')
        else:
            print('Commands: list, validate, info')
    else:
        list_all_stations()
        print('\nUsage:')
        print('  python load_stations.py list              # List all stations')
        print('  python load_stations.py validate KAK,HER  # Validate codes')
        print('  python load_stations.py info KAK         # Get station info')

```

---

## templates\index.html

```html
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GEMPRA - Geomagnetic Earthquake Monitoring using PRA</title>
    <meta name="description"
        content="Sistem Pemantauan Gempa Bumi Geomagnetik menggunakan PRA - Real-time earthquake precursor detection using Polarization Ratio Analysis">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link
        href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap"
        rel="stylesheet">
    <link rel="stylesheet" href="static/style.css">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
</head>

<body class="light-mode">
    <div class="page-shell"></div>
    <div class="container">
        <header>
            <div class="header-content">
                <h1>
                    <span class="icon">G</span>
                    GEMPRA
                </h1>
                <p class="hero-kicker">Geomagnetic precursor observation dashboard</p>
                <p class="subtitle">Geomagnetic Earthquake Monitoring using PRA</p>
                <p class="subtitle-malay">Sistem Pemantauan Gempa Bumi Geomagnetik menggunakan PRA</p>
                <p class="subtitle-explanation">
                    PRA = Polarization Ratio Analysis | Analisis Nisbah Polarisasi
                </p>

                <div class="header-controls">
                    <div class="date-selector-container">
                        <label for="date-selector">Select Date:</label>
                        <select id="date-selector">
                            <option value="">Loading dates...</option>
                        </select>
                    </div>
                    <div class="mode-toggle-container">
                        <span class="mode-label">Dark</span>
                        <label class="toggle-switch">
                            <input type="checkbox" id="dark-mode-toggle">
                            <span class="slider"></span>
                        </label>
                    </div>
                </div>
                <p class="timestamp">Last updated: <span id="timestamp">Loading...</span></p>
            </div>
        </header>

        <div class="summary-stats" id="summary-stats"></div>
        <div class="run-health" id="run-health"></div>

        <div class="analytics-section">
            <div class="analytics-grid">
                <div class="chart-card">
                    <h3 class="chart-title">7-Day Anomaly Trend</h3>
                    <canvas id="trend-chart"></canvas>
                </div>
                <div class="chart-card">
                    <h3 class="chart-title">Station Status</h3>
                    <canvas id="distribution-chart"></canvas>
                </div>
                <div class="chart-card">
                    <h3 class="chart-title">Detection Success Rate</h3>
                    <canvas id="success-rate-chart"></canvas>
                </div>
                <div class="chart-card">
                    <h3 class="chart-title">Magnitude Distribution</h3>
                    <canvas id="magnitude-chart"></canvas>
                </div>
            </div>
        </div>

        <div class="main-content-layout">
            <div class="map-section">
                <div class="section-header">
                    <h2>Station Map</h2>
                    <div class="section-actions">
                        <button class="btn-download" id="download-anomalies-btn" title="Download Anomalies CSV">
                            Download Anomalies
                        </button>
                    </div>
                </div>
                <div id="map-container" class="map-container"></div>
                <div class="map-legend" id="map-legend"></div>
            </div>

            <div class="plot-panel-section">
                <div class="plot-panel">
                    <div class="plot-panel-header">
                        <h2 class="panel-title">Station Analysis</h2>
                    </div>
                    <div class="plot-panel-content">
                        <div class="selector-container">
                            <label class="selector-label">Select Station:</label>
                            <select class="station-selector" id="station-selector">
                                <option value="">Select a station...</option>
                            </select>
                        </div>
                        <div class="selected-station-plot" id="selected-station-plot"></div>
                    </div>
                </div>
            </div>
        </div>

        <footer>
            <p class="method-info">
                Method: Multitaper Spectral Analysis (NW=3.5) + Extreme Value Theory (EVT)<br>
                Frequency Band: 0.095-0.110 Hz | Time Window: 20:00-04:00 Local Time
            </p>

            <div class="footer-grid">
                <div class="acknowledgements">
                    <h3>Acknowledgements</h3>
                    <ul>
                        <li>Data provided by <a href="https://www.intermagnet.org" target="_blank">INTERMAGNET</a>
                            (International Real-time Magnetic Observatory Network)</li>
                        <li>Earthquake data from <a href="https://earthquake.usgs.gov" target="_blank">USGS</a> (United
                            States Geological Survey)</li>
                        <li>Research conducted at <a href="https://www.upm.edu.my" target="_blank">Universiti Putra
                                Malaysia</a></li>
                    </ul>
                </div>

                <div class="author">
                    <p>Developed by <a href="https://github.com/syaifulafrizal" target="_blank">Nur Syaiful Afrizal</a></p>
                </div>
            </div>

            <div class="copyright-line">
                <p>&copy; Universiti Putra Malaysia. All rights reserved.</p>
            </div>
        </footer>
    </div>

    <script src="static/app.js"></script>
</body>

</html>
```

---

## static\style.css

```css
/* PRA Dashboard Styles with Dark/Light Mode Support */

:root {
    --bg-primary: #f3efe4;
    --bg-secondary: rgba(255, 252, 246, 0.84);
    --bg-tertiary: rgba(248, 241, 227, 0.9);
    --surface-strong: #fffdf8;
    --text-primary: #1a2233;
    --text-secondary: #5f6c7b;
    --accent-primary: #0d6e6e;
    --accent-secondary: #c76a2a;
    --accent-success: #1d8f5a;
    --accent-warning: #cc8a1d;
    --border-color: rgba(25, 34, 51, 0.1);
    --shadow: rgba(21, 35, 52, 0.08);
    --shadow-strong: rgba(21, 35, 52, 0.16);
}

.dark-mode {
    --bg-primary: #09111c;
    --bg-secondary: rgba(15, 27, 42, 0.84);
    --bg-tertiary: rgba(22, 39, 60, 0.92);
    --surface-strong: #142338;
    --text-primary: #f4f7fb;
    --text-secondary: #9bacbf;
    --accent-primary: #53d0cb;
    --accent-secondary: #f6b15b;
    --accent-success: #4ed09d;
    --accent-warning: #f0b84d;
    --border-color: rgba(163, 191, 221, 0.16);
    --shadow: rgba(0, 0, 0, 0.28);
    --shadow-strong: rgba(0, 0, 0, 0.42);
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Manrope', 'Segoe UI', sans-serif;
    background:
        radial-gradient(circle at top left, rgba(199, 106, 42, 0.16), transparent 28%),
        radial-gradient(circle at top right, rgba(13, 110, 110, 0.18), transparent 30%),
        linear-gradient(180deg, #f8f4ea 0%, #eef2f5 52%, #f6f2e7 100%);
    color: var(--text-primary);
    min-height: 100vh;
    transition: background 0.3s ease, color 0.3s ease;
    line-height: 1.6;
    position: relative;
}

.dark-mode body,
body.dark-mode {
    background:
        radial-gradient(circle at top left, rgba(246, 177, 91, 0.14), transparent 24%),
        radial-gradient(circle at top right, rgba(83, 208, 203, 0.12), transparent 28%),
        linear-gradient(180deg, #0a1320 0%, #101c2d 52%, #0d1726 100%);
}

.page-shell {
    position: fixed;
    inset: 0;
    pointer-events: none;
    background-image:
        linear-gradient(rgba(255, 255, 255, 0.06) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.06) 1px, transparent 1px);
    background-size: 32px 32px;
    mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.28), transparent 80%);
    opacity: 0.35;
}

.container {
    max-width: 1440px;
    margin: 0 auto;
    padding: 28px 24px 40px;
    position: relative;
    z-index: 1;
}

/* Header Styles */
header {
    background:
        linear-gradient(135deg, rgba(13, 110, 110, 0.12), rgba(199, 106, 42, 0.06)),
        var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 26px;
    padding: 36px 40px;
    margin-bottom: 28px;
    box-shadow: 0 18px 45px var(--shadow);
    backdrop-filter: blur(16px);
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 20px;
}

.header-left h1 {
    font-size: 2rem;
    color: var(--text-primary);
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    gap: 12px;
}

.header-left .icon {
    font-size: 2.2rem;
}

.hero-kicker {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 14px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.62);
    border: 1px solid rgba(255, 255, 255, 0.55);
    color: var(--accent-primary);
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin: 0 auto 14px;
}

.header-left .subtitle {
    color: var(--text-secondary);
    font-size: 0.95rem;
    margin-bottom: 2px;
}

.header-left .subtitle-malay {
    color: var(--text-secondary);
    font-size: 0.85rem;
    font-style: italic;
    opacity: 0.8;
}

.header-right {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 12px;
}

.header-controls {
    display: flex;
    gap: 16px;
    align-items: center;
}

.date-selector-container label {
    margin-right: 8px;
    color: var(--text-secondary);
    font-size: 0.9rem;
}

.date-selector-container select {
    padding: 8px 12px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--bg-secondary);
    color: var(--text-primary);
    font-size: 0.9rem;
    cursor: pointer;
}

.mode-toggle-container {
    display: flex;
    align-items: center;
    gap: 8px;
}

.mode-label {
    font-size: 0.9rem;
    color: var(--text-secondary);
}

.toggle-switch {
    position: relative;
    display: inline-block;
    width: 50px;
    height: 24px;
}

.toggle-switch input {
    opacity: 0;
    width: 0;
    height: 0;
}

.slider {
    position: absolute;
    cursor: pointer;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: #ccc;
    transition: 0.4s;
    border-radius: 24px;
}

.slider:before {
    position: absolute;
    content: "";
    height: 18px;
    width: 18px;
    left: 3px;
    bottom: 3px;
    background-color: white;
    transition: 0.4s;
    border-radius: 50%;
}

input:checked+.slider {
    background-color: var(--accent-primary);
}

input:checked+.slider:before {
    transform: translateX(26px);
}

.timestamp {
    font-size: 0.85rem;
    color: var(--text-secondary);
}

/* Summary Stats */
.summary-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 20px;
    margin-bottom: 24px;
}

.metric-card {
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.5), rgba(255, 255, 255, 0.16)), var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 22px;
    padding: 24px;
    box-shadow: 0 12px 24px var(--shadow);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    backdrop-filter: blur(14px);
}

.metric-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 18px 32px var(--shadow-strong);
}

.metric-card h3 {
    font-size: 0.9rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 12px;
}

.metric-card .value {
    font-size: 2.5rem;
    font-weight: bold;
    color: var(--text-primary);
    margin-bottom: 8px;
}

.metric-card .label {
    font-size: 0.85rem;
    color: var(--text-secondary);
}

.metric-card.progress .progress-bar {
    height: 8px;
    background: var(--bg-tertiary);
    border-radius: 4px;
    margin-top: 12px;
    overflow: hidden;
}

.metric-card.progress .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent-primary), var(--accent-success));
    transition: width 0.3s ease;
}

.metric-card.warning {
    border-left: 4px solid var(--accent-warning, #f39c12);
}

.run-health {
    background: linear-gradient(120deg, rgba(13, 110, 110, 0.08), rgba(199, 106, 42, 0.05)), var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 22px;
    padding: 24px;
    box-shadow: 0 14px 28px var(--shadow);
    margin-bottom: 24px;
    backdrop-filter: blur(14px);
}

.run-health h3 {
    margin-bottom: 12px;
    font-size: 1.2rem;
}

.run-health .health-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 16px;
    margin-bottom: 16px;
}

.run-health .health-item {
    padding: 14px 16px;
    border: 1px solid var(--border-color);
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.28);
}

.run-health .health-label {
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-bottom: 4px;
}

.run-health .health-value {
    font-size: 1.4rem;
    font-weight: 600;
}

.run-health .health-meta {
    font-size: 0.85rem;
    color: var(--text-secondary);
}

.run-health .history-links a {
    color: var(--accent-secondary);
    text-decoration: none;
    margin-right: 12px;
    font-size: 0.9rem;
}

.run-health .history-links a:hover {
    text-decoration: underline;
}

.metric-card.warning .value {
    color: var(--accent-warning, #f39c12);
}

/* Main Content Layout */
.main-content-layout {
    display: flex;
    flex-direction: column;
    gap: 24px;
    margin-bottom: 24px;
}

/* Map Section */
.map-section {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 24px;
    padding: 24px;
    box-shadow: 0 16px 34px var(--shadow);
    backdrop-filter: blur(16px);
}

.section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
}

.section-header h2 {
    font-size: 1.5rem;
    color: var(--text-primary);
}

.section-actions {
    display: flex;
    gap: 12px;
}

.btn-download {
    padding: 12px 20px;
    background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
    color: white;
    border: none;
    border-radius: 999px;
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 700;
    letter-spacing: 0.02em;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    box-shadow: 0 10px 18px rgba(13, 110, 110, 0.2);
}

.btn-download:hover {
    transform: translateY(-1px);
    box-shadow: 0 14px 24px rgba(13, 110, 110, 0.26);
}

.map-container {
    width: 100%;
    height: 600px;
    border-radius: 18px;
    overflow: hidden;
    background: var(--bg-tertiary);
    min-height: 600px;
    border: 1px solid var(--border-color);
}

.map-legend {
    margin-top: 16px;
    padding: 16px;
    background: var(--bg-tertiary);
    border-radius: 8px;
    font-size: 0.85rem;
    color: var(--text-secondary);
}

/* Map legend control (Leaflet control) */
.map-legend-control {
    background: rgba(255, 255, 255, 0.95) !important;
    padding: 12px !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3) !important;
    font-size: 12px !important;
    line-height: 1.6 !important;
    color: #2c3e50 !important;
    border: 1px solid rgba(0, 0, 0, 0.1) !important;
}

.dark-mode .map-legend-control {
    background: rgba(37, 40, 54, 0.95) !important;
    color: #ecf0f1 !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5) !important;
}

.map-legend-control .legend-title {
    font-weight: bold;
    margin-bottom: 8px;
    color: #2c3e50;
}

.dark-mode .map-legend-control .legend-title {
    color: #ecf0f1;
}

.map-legend-control .legend-item {
    margin-bottom: 6px;
    color: #2c3e50;
}

.dark-mode .map-legend-control .legend-item {
    color: #ecf0f1;
}

.map-legend-control .legend-divider {
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid #ddd;
}

.dark-mode .map-legend-control .legend-divider {
    border-top-color: rgba(255, 255, 255, 0.2);
}

/* Plot Panel */
.plot-panel-section {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 24px;
    padding: 24px;
    box-shadow: 0 16px 34px var(--shadow);
    width: 100%;
    backdrop-filter: blur(16px);
}

.plot-panel-header h2 {
    font-size: 1.5rem;
    color: var(--text-primary);
    margin-bottom: 20px;
}

.selector-container {
    margin-bottom: 20px;
}

.selector-label {
    display: block;
    margin-bottom: 8px;
    color: var(--text-secondary);
    font-size: 0.9rem;
}

.station-selector {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--bg-secondary);
    color: var(--text-primary);
    font-size: 0.95rem;
    cursor: pointer;
}

.selected-station-plot {
    margin-top: 20px;
    min-height: 600px;
    width: 100%;
}

.selected-station-plot img {
    width: 100%;
    height: auto;
    max-width: 100%;
    min-height: 600px;
    object-fit: contain;
    border-radius: 8px;
    box-shadow: 0 2px 4px var(--shadow);
}

.plot-image-container {
    width: 100%;
    margin-top: 20px;
}

.plot-image-container img,
.plot-image-container .plot-image {
    width: 100%;
    height: auto;
    min-height: 600px;
    max-height: 800px;
    object-fit: contain;
    border-radius: 8px;
    box-shadow: 0 2px 4px var(--shadow);
}

/* Footer */
footer {
    background:
        linear-gradient(135deg, rgba(13, 110, 110, 0.1), rgba(199, 106, 42, 0.06)),
        var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 26px;
    padding: 32px;
    margin-top: 24px;
    box-shadow: 0 18px 38px var(--shadow);
    backdrop-filter: blur(16px);
}

.method-info {
    color: var(--text-secondary);
    font-size: 0.9rem;
    margin-bottom: 24px;
    line-height: 1.6;
}

.footer-grid {
    display: grid;
    grid-template-columns: minmax(0, 2fr) minmax(260px, 1fr);
    gap: 28px;
    align-items: start;
}

.acknowledgements h3 {
    color: var(--text-primary);
    font-size: 1.1rem;
    margin-bottom: 12px;
}

.acknowledgements ul {
    list-style: none;
    color: var(--text-secondary);
    font-size: 0.9rem;
    line-height: 1.8;
}

.acknowledgements a {
    color: var(--accent-primary);
    text-decoration: none;
}

.acknowledgements a:hover {
    text-decoration: underline;
}

.author {
    margin-top: 0;
    padding: 18px 20px;
    border: 1px solid var(--border-color);
    border-radius: 18px;
    text-align: left;
    color: var(--text-secondary);
    font-size: 0.95rem;
    background: rgba(255, 255, 255, 0.22);
}

.author a {
    color: var(--accent-primary);
    text-decoration: none;
}

.author a:hover {
    text-decoration: underline;
}

.copyright-line {
    margin-top: 24px;
    padding-top: 20px;
    border-top: 1px solid var(--border-color);
    text-align: center;
    color: var(--text-secondary);
    font-size: 0.84rem;
    letter-spacing: 0.03em;
}

/* Map Markers */
.station-marker {
    background: transparent;
    border: none;
}

/* Triangle marker for stations - SOLID FILL */
.marker-triangle {
    width: 0;
    height: 0;
    border-left: 12px solid transparent;
    border-right: 12px solid transparent;
    border-bottom: 20px solid;
    border-top: 0;
    position: relative;
    filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.4));
}

/* Solid filled triangles with white border */
.marker-triangle.marker-gray {
    border-bottom-color: #95a5a6;
}

.marker-triangle.marker-eq-reliable {
    border-bottom-color: #f39c12;
}

.marker-triangle.marker-eq-false {
    border-bottom-color: #e74c3c;
}

/* Legacy circle marker (kept for backward compatibility, but not used) */
.marker-dot {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 3px solid white;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
}

.marker-dot.marker-gray {
    background: #95a5a6;
}

.marker-dot.marker-eq-reliable {
    background: #f39c12;
}

.marker-dot.marker-eq-false {
    background: #e74c3c;
}

/* Responsive */
@media (max-width: 768px) {
    header {
        flex-direction: column;
        align-items: flex-start;
    }

    .header-right {
        align-items: flex-start;
        width: 100%;
    }

    .summary-stats {
        grid-template-columns: 1fr;
    }

    .main-content-layout {
        grid-template-columns: 1fr;
    }

    .map-container {
        height: 400px;
        min-height: 400px;
    }
}
/* Header Content - Centered Layout */
.header-content {
    max-width: 880px;
    margin: 0 auto;
    text-align: center;
}

.header-content h1 {
    font-family: 'Space Grotesk', 'Manrope', sans-serif;
    font-size: 3rem !important;
    font-weight: 700;
    justify-content: center !important;
    letter-spacing: -0.05em;
    margin-bottom: 10px;
}

.header-content .icon {
    width: 54px;
    height: 54px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 18px;
    background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
    color: #fff;
    font-size: 1.5rem;
    box-shadow: 0 14px 24px rgba(13, 110, 110, 0.22);
}

.header-content .subtitle {
    font-size: 1rem;
    font-weight: 500;
}

.header-content .subtitle-malay {
    font-size: 0.875rem;
    margin-bottom: 20px;
}

.subtitle-explanation {
    font-size: 0.82rem;
    color: var(--text-secondary);
    margin-top: 8px;
    font-style: italic;
}

.header-controls {
    justify-content: center;
    margin-top: 16px;
    flex-wrap: wrap;
    gap: 14px;
}

/* Analytics Section with Charts */
.analytics-section {
    margin-bottom: 24px;
}

.analytics-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 20px;
}

.chart-card {
    background: var(--bg-secondary);
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 1px 3px var(--shadow);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.chart-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px var(--shadow);
}

.chart-title {
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 16px;
}

.chart-card canvas {
    max-height: 200px;
}

/* Mobile Responsive */
@media (max-width: 768px) {
    header {
        padding: 20px;
    }
    
    .header-content h1 {
        font-size: 1.75rem !important;
    }

    .hero-kicker {
        font-size: 0.68rem;
    }
    
    .analytics-grid {
        grid-template-columns: 1fr;
    }

    .footer-grid {
        grid-template-columns: 1fr;
    }

    .container {
        padding: 18px 14px 28px;
    }
}


/* Enhanced Chart Card Styles */
.chart-card {
    border: 1px solid var(--border-color);
    border-radius: 22px;
    box-shadow: 0 14px 26px var(--shadow);
    backdrop-filter: blur(14px);
}

.chart-card:hover {
    box-shadow: 0 18px 32px var(--shadow-strong);
}

/* Better metric card styling */
.metric-card {
    box-shadow: 0 14px 26px var(--shadow);
}

.metric-card:hover {
    box-shadow: 0 18px 32px var(--shadow-strong);
}

/* Improve fallback notice readability */
.fallback-notice {
    background: rgba(243, 156, 18, 0.15) !important;
    border-left: 4px solid var(--accent-warning) !important;
    color: var(--text-primary) !important;
}
```

---

## static\app.js

```javascript
// Enhanced frontend JavaScript for PRA Dashboard with Map - Earthquake Theme

const DATA_URL = 'data/stations.json';

let allStationsData = {};
let stationMetadata = {};
let map = null;
let markers = {};
let allStations = [];
let anomalousStations = [];
let availableDates = [];
let selectedDate = null;
let mostRecentDate = null;
let isAggregatedDataLoaded = false;


// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Set up dark mode toggle
    const darkModeToggle = document.getElementById('dark-mode-toggle');
    if (darkModeToggle) {
        // Load saved preference
        const savedMode = localStorage.getItem('darkMode');
        if (savedMode === 'true') {
            document.body.classList.add('dark-mode');
            darkModeToggle.checked = true;
        }

        darkModeToggle.addEventListener('change', (e) => {
            if (e.target.checked) {
                document.body.classList.add('dark-mode');
                localStorage.setItem('darkMode', 'true');
            } else {
                document.body.classList.remove('dark-mode');
                localStorage.setItem('darkMode', 'false');
            }
        });
    }

    // Set up date selector
    const dateSelector = document.getElementById('date-selector');
    if (dateSelector) {
        dateSelector.addEventListener('change', (e) => {
            const newDate = e.target.value;
            if (newDate) {
                selectedDate = newDate; // Update global variable
                renderDashboard(newDate);
            }
        });
    }

    // Set up CSV download button
    const downloadBtn = document.getElementById('download-anomalies-btn');
    if (downloadBtn) {
        downloadBtn.addEventListener('click', downloadAnomaliesCSV);
    }

    // Populate date selector immediately from stations.json
    populateDateSelectorFromMetadata().then(() => {
        // Wait a bit for date selector to populate, then render
        setTimeout(() => {
            renderDashboard();
        }, 100);
    }).catch(error => {
        console.error('Error populating date selector:', error);
        // Still try to render even if date selector fails
        renderDashboard();
    });
    setInterval(() => {
        // Auto-refresh with current selected date
        const currentDate = document.getElementById('date-selector')?.value || selectedDate;
        renderDashboard(currentDate);
    }, 300000); // Auto-refresh every 5 minutes
});

async function loadData(date = null) {
    try {
        // First, load stations.json to get available dates
        const response = await fetch(DATA_URL);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const metadata = await response.json();

        // Extract available dates and most recent date
        availableDates = metadata.available_dates || [];
        mostRecentDate = metadata.most_recent_date || null;

        // If no date specified, use most recent
        if (!date && mostRecentDate) {
            date = mostRecentDate;
            selectedDate = date;
        } else if (!date) {
            // Fallback to today if no dates available
            date = new Date().toISOString().split('T')[0];
            selectedDate = date;
        } else {
            selectedDate = date;
        }

        // Validate that the selected date is in available dates
        // If not, use the most recent date instead
        if (availableDates.length > 0 && !availableDates.includes(date)) {
            console.warn(`Selected date ${date} not in available dates. Using most recent: ${mostRecentDate}`);
            date = mostRecentDate || availableDates[0];
            selectedDate = date;
        }

        // OPTIMIZATION: Load aggregated data file for the selected date
        // This replaces 100+ individual station requests with a single request
        console.log(`Loading aggregated data for ${date}...`);
        const aggregatedUrl = `data/aggregated_${date}.json`;

        try {
            const aggregatedResponse = await fetch(aggregatedUrl, { cache: 'no-cache' });

            if (aggregatedResponse.ok) {
                const aggregatedData = await aggregatedResponse.json();
                console.log(`âœ“ Loaded aggregated data for ${date} (${Object.keys(aggregatedData.stations || {}).length} stations)`);
                isAggregatedDataLoaded = true;

                // Transform aggregated data to match expected format
                const dateData = aggregatedData.stations || {};
                const stationDates = {};

                // Track which date each station is using (all using same date from aggregated file)
                for (const station of Object.keys(dateData)) {
                    stationDates[station] = aggregatedData.date || date;
                }

                // Store earthquake correlations and false negatives for later use
                window.earthquakeCorrelations = aggregatedData.earthquake_correlations || {};
                window.falseNegatives = aggregatedData.false_negatives || {};

                return {
                    stations: metadata.stations || Object.keys(dateData),
                    data: dateData,
                    metadata: aggregatedData.metadata || metadata.metadata || {},
                    available_dates: availableDates,
                    most_recent_date: mostRecentDate,
                    selected_date: date,
                    station_dates: stationDates
                };
            } else {
                console.warn(`Aggregated data not found for ${date}, falling back to individual files`);
                isAggregatedDataLoaded = false;
                // Fall back to old method if aggregated file doesn't exist
                return await loadDataFallback(date, metadata, availableDates, mostRecentDate);
            }
        } catch (error) {
            console.warn(`Error loading aggregated data for ${date}:`, error);
            isAggregatedDataLoaded = false;
            // Fall back to old method on error
            return await loadDataFallback(date, metadata, availableDates, mostRecentDate);
        }
    } catch (error) {
        console.error('Error loading data:', error);
        return null;
    }
}

// Fallback function for loading individual station files (kept for compatibility)
async function loadDataFallback(date, metadata, availableDates, mostRecentDate) {
    console.log('Using fallback method: loading individual station files...');

    const dateData = {};
    const stationDates = {};
    let hasAnyData = false;

    // Only try the selected date (no complex fallback logic)
    for (const station of (metadata.stations || [])) {
        try {
            const stationResponse = await fetch(`data/${station}_${date}.json`, { cache: 'no-cache' });
            if (stationResponse.ok) {
                const stationData = await stationResponse.json();
                dateData[station] = stationData;
                stationDates[station] = stationData?.date || date;
                hasAnyData = true;
            }
        } catch (error) {
            // Silently skip stations without data
            console.debug(`Station ${station}: No data for ${date}`);
        }
    }

    if (!hasAnyData) {
        return null;
    }

    return {
        stations: metadata.stations || [],
        data: dateData,
        metadata: metadata.metadata || [],
        available_dates: availableDates,
        most_recent_date: mostRecentDate,
        selected_date: date,
        station_dates: stationDates
    };
}

async function loadEarthquakeCorrelations(station, date = null) {
    // OPTIMIZATION: Use cached data from aggregated file if available
    if (window.earthquakeCorrelations && window.earthquakeCorrelations[station]) {
        const correlations = window.earthquakeCorrelations[station];
        // Filter by magnitude >= 5.0 for reliability
        return correlations.filter(eq => parseFloat(eq.earthquake_magnitude || eq.magnitude || 0) >= 5.0);
    }

    // If we loaded aggregated data successfully but found no correlations for this station,
    // assume there are none (don't make 404 requests)
    if (isAggregatedDataLoaded) {
        return [];
    }

    // Fallback: Load from individual CSV file
    try {
        // Try date-specific file first if date is provided
        if (date) {
            try {
                const dateResponse = await fetch(`data/${station}_${date}_earthquake_correlations.json`);
                if (dateResponse.ok) {
                    const data = await dateResponse.json();
                    // Handle both array and object formats
                    const correlations = Array.isArray(data) ? data : (data.correlations || []);
                    // Filter by magnitude >= 5.0 for reliability
                    return correlations.filter(eq => parseFloat(eq.earthquake_magnitude || eq.magnitude || 0) >= 5.0);
                }
            } catch (error) {
                // Fallback to CSV
            }
        }

        // Fallback to static CSV file
        const response = await fetch(`data/${station}_earthquake_correlations.csv`);
        if (!response.ok) {
            // Silently return empty array if CSV doesn't exist
            return [];
        }
        const text = await response.text();
        const correlations = parseCSV(text);
        // Filter by magnitude >= 5.0 for reliability
        return correlations.filter(eq => parseFloat(eq.earthquake_magnitude || 0) >= 5.0);
    } catch (error) {
        // Silently return empty array - CSV files are optional
        return [];
    }
}

async function loadFalseNegatives(station, date = null) {
    // OPTIMIZATION: Use cached data from aggregated file if available
    if (window.falseNegatives && window.falseNegatives[station]) {
        return window.falseNegatives[station];
    }

    // If we loaded aggregated data successfully but found no false negatives for this station,
    // assume there are none (don't make 404 requests)
    if (isAggregatedDataLoaded) {
        return [];
    }

    // Fallback: Load from individual CSV file
    try {
        // Try date-specific file first if date is provided
        if (date) {
            try {
                const dateResponse = await fetch(`data/${station}_${date}_false_negatives.json`);
                if (dateResponse.ok) {
                    const data = await dateResponse.json();
                    // Handle both array and object formats
                    return Array.isArray(data) ? data : (data.false_negatives || []);
                }
            } catch (error) {
                // Fallback to CSV
            }
        }

        // Fallback to static CSV file
        const response = await fetch(`data/${station}_false_negatives.csv`);
        if (!response.ok) {
            // Silently return empty array if CSV doesn't exist
            return [];
        }
        const text = await response.text();
        return parseCSV(text);
    } catch (error) {
        // Silently return empty array - CSV files are optional
        return [];
    }
}

async function loadRecentEarthquakes(date = null) {
    // Load earthquake data for the specified date only (no fallback)
    // Use selectedDate if no date provided
    if (!date) {
        date = selectedDate || new Date().toISOString().split('T')[0];
    }

    // Only try the specified date
    try {
        const response = await fetch(`data/recent_earthquakes_${date}.csv`);
        if (response.ok) {
            const text = await response.text();
            return parseCSV(text);
        }
    } catch (error) {
        // Return empty array if file doesn't exist
    }

    return [];
}

function parseCSV(csvText) {
    const lines = csvText.split('\n').filter(line => line.trim());
    if (lines.length < 2) return [];

    const headers = lines[0].split(',').map(h => h.trim());
    const data = [];

    for (let i = 1; i < lines.length; i++) {
        const values = lines[i].split(',').map(v => v.trim());
        const row = {};
        headers.forEach((header, idx) => {
            row[header] = values[idx] || '';
        });
        data.push(row);
    }

    return data;
}

function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

function formatDateForSelector(dateStr) {
    if (!dateStr) return 'Unknown Date';

    // Clean date string to ensure YYYY-MM-DD format
    let cleanDateStr = dateStr;
    if (dateStr.includes('T')) {
        cleanDateStr = dateStr.split('T')[0];
    } else if (dateStr.includes(' ')) {
        cleanDateStr = dateStr.split(' ')[0];
    }

    // Add T00:00:00 to force local time parsing (prevent timezone shifts)
    const date = new Date(cleanDateStr + 'T00:00:00');

    // Fallback if parsing failed
    if (isNaN(date.getTime())) {
        return dateStr;
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    const dateOnly = new Date(date);
    dateOnly.setHours(0, 0, 0, 0);

    let label = date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });

    if (dateOnly.getTime() === today.getTime()) {
        label += ' (Today)';
    } else if (dateOnly.getTime() === yesterday.getTime()) {
        label += ' (Yesterday)';
    }

    return label;
}

async function fetchHistoryFile(filename) {
    try {
        const response = await fetch(`data/${filename}`, { cache: 'no-cache' });
        if (response.ok) {
            return await response.json();
        }
    } catch (error) {
        console.debug(`Failed to load ${filename}:`, error);
    }
    return { entries: [] };
}

async function getAnomalyHistory() {
    return await fetchHistoryFile('anomaly_history.json');
}

async function getFalseNegativeHistory() {
    return await fetchHistoryFile('false_negative_history.json');
}

async function populateDateSelectorFromMetadata() {
    try {
        const response = await fetch(DATA_URL);
        if (!response.ok) {
            console.error('Failed to load stations.json:', response.status);
            return;
        }
        const metadata = await response.json();

        const dateSelector = document.getElementById('date-selector');
        if (dateSelector && metadata.available_dates && metadata.available_dates.length > 0) {
            dateSelector.innerHTML = '';
            metadata.available_dates.forEach(date => {
                const option = document.createElement('option');
                option.value = date;
                option.textContent = formatDateForSelector(date);
                if (date === metadata.most_recent_date) {
                    option.selected = true;
                    selectedDate = date;
                }
                dateSelector.appendChild(option);
            });

            // Store for later use
            availableDates = metadata.available_dates || [];
            mostRecentDate = metadata.most_recent_date || null;
        }
    } catch (error) {
        console.error('Error populating date selector:', error);
    }
}

function initMap() {
    const mapContainer = document.getElementById('map-container');
    if (!mapContainer) {
        console.error('Map container not found');
        return;
    }

    if (map) {
        try {
            map.remove();
        } catch (e) { }
    }

    try {
        map = L.map('map-container', {
            minZoom: 2,  // Prevent zooming out too far
            maxZoom: 10, // Limit maximum zoom
            zoomControl: true
        }).setView([20, 0], 2);

        // Set max bounds to prevent panning too far
        const southWest = L.latLng(-85, -180);
        const northEast = L.latLng(85, 180);
        const bounds = L.latLngBounds(southWest, northEast);
        map.setMaxBounds(bounds);

        // Add OpenStreetMap tiles with earthquake-themed styling
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: 'Â© OpenStreetMap contributors',
            minZoom: 2,
            maxZoom: 10
        }).addTo(map);

        // Define addEarthquakeCircle function
        window.addEarthquakeCircle = function (lat, lng) {
            if (!map) return;
            // Create a dashed red circle with 200km radius centered on station
            const circle = L.circle([lat, lng], {
                color: '#e74c3c',       // Red color
                weight: 2,
                opacity: 0.8,
                fillColor: '#e74c3c',
                fillOpacity: 0.1,
                radius: 200000,         // 200km in meters
                dashArray: '10, 10'     // Dashed line pattern
            }).addTo(map);

            if (!markers.earthquakeCircles) {
                markers.earthquakeCircles = [];
            }
            markers.earthquakeCircles.push(circle);
            return circle;
        };

        // Legend is now outside the map - see createStandaloneLegend() function

        // Clear existing markers and circles
        if (markers.earthquakes) {
            markers.earthquakes.forEach(m => {
                try { m.remove(); } catch (e) { }
            });
        }
        if (markers.earthquakeCircles) {
            markers.earthquakeCircles.forEach(c => {
                try { c.remove(); } catch (e) { }
            });
        }
        Object.keys(markers).forEach(key => {
            if (key !== 'earthquakes' && key !== 'earthquakeCircles') {
                try {
                    if (Array.isArray(markers[key])) {
                        markers[key].forEach(m => m.remove());
                    } else {
                        markers[key].remove();
                    }
                } catch (e) { }
            }
        });
        markers = {};
    } catch (error) {
        console.error('Error creating map:', error);
    }
}

function addStationToMap(stationCode, stationData, eqCorrelations, dataContext = null, falseNegatives = []) {
    if (!map) {
        console.warn('Map not initialized, skipping marker for', stationCode);
        return;
    }

    const metadata = stationMetadata[stationCode];
    if (!metadata || !metadata.latitude || !metadata.longitude) {
        console.warn(`Missing metadata for ${stationCode}`);
        return;
    }

    // Determine status
    const hasAnomaly = stationData && stationData.is_anomalous;
    const hasEQ = eqCorrelations && eqCorrelations.length > 0;
    const hasFN = falseNegatives && falseNegatives.length > 0;

    // Earthquake-themed colors
    let color = 'gray'; // No anomaly
    if (hasAnomaly) {
        // Check if we have a True Positive or False Positive
        const isTP = hasEQ && eqCorrelations.some(eq => eq.status === 'TP' || !eq.status); // Default to TP if status not set (legacy)
        const isFP = hasEQ && eqCorrelations.every(eq => eq.status === 'FP');

        if (isTP) color = 'eq-reliable'; // Orange/Red
        else if (isFP) color = 'eq-false'; // Red (Alarm without EQ)
        else if (!hasEQ) color = 'eq-false'; // Red (Alarm without EQ)
    }
    // False Negatives (Missed EQ) will remain 'gray' but show info in popup

    // Create custom icon with earthquake theme (triangle shape for stations)
    const icon = L.divIcon({
        className: 'station-marker',
        html: `<div class="marker-triangle marker-${color}"></div>`,
        iconSize: [24, 24],
        iconAnchor: [12, 20] // Anchor at bottom center of triangle
    });

    // Get the date being used for this station (from stationData or station_dates)
    const stationDateUsed = stationData?.date || (dataContext?.station_dates && dataContext.station_dates[stationCode]) || 'Unknown';
    const isUsingFallback = dataContext?.selected_date && stationDateUsed !== dataContext.selected_date;

    // Create popup content with earthquake info
    let popupContent = `<div style="min-width: 240px; font-family: Arial, sans-serif;"><strong style="color: #c0392b; font-size: 1.1em;">${metadata.name || stationCode} (${stationCode})</strong><br>`;
    popupContent += `<span style="color: #7f8c8d;">${metadata.country || 'Unknown'}</span><br>`;
    popupContent += `<small>ðŸ“ ${metadata.latitude ? metadata.latitude.toFixed(3) : 'N/A'}, ${metadata.longitude ? metadata.longitude.toFixed(3) : 'N/A'}</small><br>`;

    // Show data date with fallback indicator
    if (isUsingFallback && dataContext?.selected_date) {
        popupContent += `<hr style="margin: 8px 0; border-color: var(--accent-warning);">`;
        popupContent += `<small style="color: var(--accent-warning);">ðŸ“… Data from: ${formatDate(stationDateUsed)}</small><br>`;
        popupContent += `<small style="color: var(--accent-warning); font-style: italic;">(Selected: ${formatDateForSelector(dataContext.selected_date)})</small><br>`;
    } else if (stationData) {
        popupContent += `<hr style="margin: 8px 0; border-color: var(--text-secondary);">`;
        popupContent += `<small style="color: var(--text-secondary);">ðŸ“… Data from: ${formatDate(stationDateUsed)}</small><br>`;
    }

    if (hasAnomaly && stationData) {
        popupContent += `<hr style="margin: 8px 0; border-color: #e74c3c;"><strong style="color: #e74c3c;">âš ï¸ Anomaly Detected</strong><br>`;
        popupContent += `ðŸ“… ${formatDate(stationData.date)}<br>`;
        popupContent += `ðŸ“Š Threshold: ${parseFloat(stationData.threshold || 0).toFixed(2)}<br>`;
        popupContent += `â±ï¸ Anomaly Hours: ${stationData.nAnomHours || 0}<br>`;

        // Filter by magnitude >= 5.0 for display
        const reliableCorrelations = eqCorrelations.filter(eq => parseFloat(eq.earthquake_magnitude || 0) >= 5.0);

        if (hasEQ && reliableCorrelations.length > 0) {
            // Check status (TP/FP)
            const status = reliableCorrelations[0].status || 'TP';
            const statusLabel = status === 'TP' ? 'True Positive' : (status === 'FP' ? 'False Positive' : status);
            const statusColor = status === 'TP' ? '#e67e22' : '#e74c3c';

            popupContent += `<hr style="margin: 8px 0; border-color: ${statusColor};"><strong style="color: ${statusColor};">${statusLabel}</strong><br>`;
            popupContent += `<span style="font-size: 0.9em;">Correlation Found (Mâ‰¥5.0): ${reliableCorrelations.length}</span><br>`;

            reliableCorrelations.slice(0, 3).forEach((eq) => {
                const mag = eq.earthquake_magnitude || 'N/A';
                const dist = parseFloat(eq.earthquake_distance_km || 0).toFixed(1);
                const days = parseFloat(eq.days_before_anomaly || 0).toFixed(1);
                popupContent += `ðŸ”´ M${mag} @ ${dist}km (${days} days before)<br>`;
            });
            if (reliableCorrelations.length > 3) {
                popupContent += `... and ${reliableCorrelations.length - 3} more<br>`;
            }
        } else {
            // Anomaly but no EQ -> Check if 14 days passed for FP
            // We can check backend status if available, or infer
            // For now, if no reliable correlations, it's a False Positive or Pending.
            // The backend usually sets 'FP' or 'Pending' in the correlations list even if empty EQ?
            // No, my backend change ADDS an entry for FP/Pending. So 'reliableCorrelations' should handle it.
            // Wait, reliableCorrelations filters by mag >= 5.0. If backend added an FP entry with no mag, it might be filtered out?
            // Need to check backend change again.
            // Backend sets: earthquake_magnitude: None. parseFloat(None) = NaN. NaN >= 5.0 is false.
            // So reliableCorrelations will be EMPTY for FP/Pending entries.
            // I need to check eqCorrelations for non-EQ entries (status entries).
            const statusEntry = eqCorrelations.find(eq => eq.status);
            if (statusEntry) {
                const status = statusEntry.status;
                const label = status === 'FP' ? 'False Positive' : 'Pending';
                popupContent += `<hr style="margin: 8px 0; border-color: #e74c3c;"><strong style="color: #e74c3c;">${label}</strong><br>`;
                popupContent += status === 'FP' ? `No EQ Mâ‰¥5.0 within 200km within 14 days` : `Monitoring for upcoming EQ...`;
            } else {
                popupContent += `<hr style="margin: 8px 0; border-color: #e74c3c;"><strong style="color: #e74c3c;">âš ï¸ False Alarm</strong><br>`;
                popupContent += `No EQ Mâ‰¥5.0 within 200km within 14 days`;
            }
        }
    } else {
        popupContent += `<hr style="margin: 8px 0; border-color: var(--text-secondary);"><span style="color: var(--text-secondary);">âœ… Status: Normal</span><br>`;
        if (hasFN) {
            popupContent += `<hr style="margin: 8px 0; border-color: #c0392b;"><strong style="color: #c0392b;">âŒ False Negative</strong><br>`;
            popupContent += `${falseNegatives.length} EQ(s) missed:<br>`;
            falseNegatives.forEach(eq => {
                const time = typeof eq.earthquake_time === 'string' ? eq.earthquake_time.split('T')[0] : eq.earthquake_time;
                popupContent += `ðŸ”´ M${eq.earthquake_magnitude} on ${time}<br>`;
            });
        } else {
            popupContent += `No anomalies detected`;
        }
    }
    popupContent += `</div>`;

    // Add marker to map
    const marker = L.marker([metadata.latitude, metadata.longitude], { icon })
        .addTo(map)
        .bindPopup(popupContent);

    markers[stationCode] = marker;

    // Add 200km red dashed circle on hover
    let hoverCircle = null;

    marker.on('mouseover', function () {
        if (hoverCircle) {
            map.removeLayer(hoverCircle);
        }
        hoverCircle = L.circle([metadata.latitude, metadata.longitude], {
            color: '#e74c3c',
            weight: 2,
            opacity: 0.8,
            fillColor: '#e74c3c',
            fillOpacity: 0.1,
            radius: 200000,
            dashArray: '10, 10',
            interactive: false // Allow events to pass through
        }).addTo(map);
    });

    marker.on('mouseout', function () {
        if (hoverCircle) {
            map.removeLayer(hoverCircle);
            hoverCircle = null;
        }
    });
}

function getEarthquakeColor(magnitude) {
    // Color gradient based on magnitude
    if (magnitude >= 8.0) return '#c0392b';  // Dark red for M8.0+
    if (magnitude >= 7.0) return '#e74c3c';  // Red for M7.0-7.9
    if (magnitude >= 6.0) return '#e67e22';  // Orange for M6.0-6.9
    return '#f1c40f';  // Yellow for M5.0-5.9
}


// ===== CHART FUNCTIONS =====
let charts = {};

function destroyCharts() {
    Object.values(charts).forEach(chart => {
        if (chart) chart.destroy();
    });
    charts = {};
}

function getChartColors() {
    const isDark = document.body.classList.contains('dark-mode');
    return {
        text: isDark ? '#f9fafb' : '#1f2937',
        grid: isDark ? '#374151' : '#e5e7eb',
        primary: isDark ? '#06b6d4' : '#0891b2',
        success: isDark ? '#34d399' : '#10b981',
        warning: isDark ? '#fbbf24' : '#f59e0b',
        danger: isDark ? '#f87171' : '#ef4444',
        gray: isDark ? '#9ca3af' : '#6b7280'
    };
}

async function create7DayTrendChart(data) {
    const ctx = document.getElementById('trend-chart');
    if (!ctx) return;

    const colors = getChartColors();
    const dates = data.available_dates.slice(-7);
    const anomalyCounts = [];

    for (const date of dates) {
        let count = 0;
        try {
            // OPTIMIZATION: Load aggregated data instead of 50+ individual requests
            const response = await fetch(`data/aggregated_${date}.json`);
            if (response.ok) {
                const aggregatedData = await response.json();
                const stationsData = aggregatedData.stations || {};

                // Count anomalies in the aggregated data
                Object.values(stationsData).forEach(stationData => {
                    if (stationData && stationData.is_anomalous) {
                        count++;
                    }
                });
            } else {
                // Fallback: If aggregated file missing (rare), try to use current loaded data 
                // if it matches the date, otherwise skip (don't spam individual requests)
                if (data.data && (data.selected_date === date || data.station_dates)) {
                    // logic to count from current data if it matches? 
                    // actually, simpler to just skip or accept 0 to avoid performance penalty.
                    // The aggregated files SHOULD exist for all valid dates now.
                    console.warn(`Aggregated file missing for trend chart: ${date}`);
                }
            }
        } catch (e) {
            console.error(`Error loading trend data for ${date}:`, e);
        }
        anomalyCounts.push(count);
    }

    charts.trend = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: dates.map(d => new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })),
            datasets: [{
                label: 'Anomalies',
                data: anomalyCounts,
                backgroundColor: colors.primary,
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { stepSize: 1, color: colors.text },
                    grid: { color: colors.grid }
                },
                x: {
                    ticks: { color: colors.text },
                    grid: { display: false }
                }
            }
        }
    });
}

function createStationDistributionChart(normalCount, withEqCount, falseAlarmCount) {
    const ctx = document.getElementById('distribution-chart');
    if (!ctx) return;

    const colors = getChartColors();

    charts.distribution = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Normal', 'With EQ', 'False Alarm'],
            datasets: [{
                data: [normalCount, withEqCount, falseAlarmCount],
                backgroundColor: [colors.gray, colors.warning, colors.danger],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: colors.text, padding: 10, font: { size: 11 } }
                }
            }
        }
    });
}

function createDetectionRateChart(successRate) {
    const ctx = document.getElementById('success-rate-chart');
    if (!ctx) return;

    const colors = getChartColors();

    charts.successRate = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Success', 'Failed'],
            datasets: [{
                data: [successRate, 100 - successRate],
                backgroundColor: [colors.success, colors.grid],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            cutout: '70%',
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => context.label + ': ' + context.parsed + '%'
                    }
                }
            }
        },
        plugins: [{
            afterDraw: (chart) => {
                const ctx = chart.ctx;
                const centerX = (chart.chartArea.left + chart.chartArea.right) / 2;
                const centerY = (chart.chartArea.top + chart.chartArea.bottom) / 2;
                ctx.save();
                ctx.font = 'bold 24px Inter';
                ctx.fillStyle = colors.text;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(Math.round(successRate) + '%', centerX, centerY);
                ctx.restore();
            }
        }]
    });
}

async function createMagnitudeDistributionChart(selectedDate) {
    const ctx = document.getElementById('magnitude-chart');
    if (!ctx) return;

    const colors = getChartColors();
    const earthquakes = await loadRecentEarthquakes(selectedDate);

    const magRanges = { 'M5-5.9': 0, 'M6-6.9': 0, 'M7-7.9': 0, 'M8+': 0 };
    earthquakes.forEach(eq => {
        const mag = parseFloat(eq.magnitude || eq.earthquake_magnitude || 0);
        if (mag >= 8.0) magRanges['M8+']++;
        else if (mag >= 7.0) magRanges['M7-7.9']++;
        else if (mag >= 6.0) magRanges['M6-6.9']++;
        else if (mag >= 5.0) magRanges['M5-5.9']++;
    });

    charts.magnitude = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: Object.keys(magRanges),
            datasets: [{
                label: 'Count',
                data: Object.values(magRanges),
                backgroundColor: ['#f1c40f', '#e67e22', '#e74c3c', '#c0392b'],
                borderRadius: 6
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    ticks: { stepSize: 1, color: colors.text },
                    grid: { color: colors.grid }
                },
                y: {
                    ticks: { color: colors.text },
                    grid: { display: false }
                }
            }
        }
    });
}

async function createAnalyticsCharts(data, normalCount, withEqCount, falseAlarmCount, successRate) {
    destroyCharts();
    await create7DayTrendChart(data);
    createStationDistributionChart(normalCount, withEqCount, falseAlarmCount);
    createDetectionRateChart(successRate);
    await createMagnitudeDistributionChart(data.selected_date);
}

function addEarthquakeMarkers(earthquakes) {
    if (!map) {
        console.warn('Map not initialized, cannot add earthquake markers');
        return;
    }

    if (!earthquakes || earthquakes.length === 0) {
        console.log('No earthquakes to display on map');
        return;
    }

    console.log(`Adding ${earthquakes.length} earthquake markers to map`);

    earthquakes.forEach((eq, index) => {
        const lat = parseFloat(eq.latitude || eq.earthquake_latitude);
        const lon = parseFloat(eq.longitude || eq.earthquake_longitude);
        const mag = parseFloat(eq.magnitude || eq.earthquake_magnitude || 0);
        const place = eq.place || eq.earthquake_place || 'Unknown';
        const time = eq.time || eq.earthquake_time || '';

        console.log(`EQ ${index + 1}: lat=${lat}, lon=${lon}, mag=${mag}, place=${place}`);

        if (isNaN(lat) || isNaN(lon)) {
            console.warn(`Skipping earthquake ${index + 1}: invalid coordinates (lat=${lat}, lon=${lon})`);
            return;
        }

        // Get color based on magnitude
        const eqColor = getEarthquakeColor(mag);

        // Create earthquake icon with magnitude-based color
        const icon = L.divIcon({
            className: 'earthquake-marker',
            html: `<div class="eq-marker" style="
                width: ${Math.max(20, Math.min(40, mag * 5))}px;
                height: ${Math.max(20, Math.min(40, mag * 5))}px;
                background: ${eqColor};
                border: 2px solid white;
                border-radius: 50%;
                box-shadow: 0 2px 8px rgba(0,0,0,0.4);
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: bold;
                font-size: ${Math.max(10, Math.min(14, mag * 2))}px;
            ">${mag.toFixed(1)}</div>`,
            iconSize: [Math.max(20, Math.min(40, mag * 5)), Math.max(20, Math.min(40, mag * 5))],
            iconAnchor: [Math.max(10, Math.min(20, mag * 2.5)), Math.max(10, Math.min(20, mag * 2.5))]
        });

        // Create popup with UTC and local time
        let timeStr = 'Unknown';
        let utcTimeStr = '';
        let localTimeStr = '';

        if (time) {
            try {
                // Parse time (could be ISO string or timestamp)
                const eqTime = new Date(time);
                if (!isNaN(eqTime.getTime())) {
                    // Format UTC time
                    utcTimeStr = eqTime.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';

                    // Format local time (at earthquake location - approximate using longitude)
                    // Rough timezone estimate: 1 hour per 15 degrees longitude
                    const localOffset = Math.round(lon / 15);
                    const localTime = new Date(eqTime.getTime() + localOffset * 3600000);
                    localTimeStr = localTime.toLocaleString('en-US', {
                        year: 'numeric',
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                        timeZoneName: 'short'
                    });

                    timeStr = `${utcTimeStr}<br><small style="color: #666;">Local (approx): ${localTimeStr}</small>`;
                }
            } catch (e) {
                timeStr = time;
            }
        }

        const popupContent = `
            <div style="min-width: 200px; font-family: Arial, sans-serif;">
                <strong style="color: #e74c3c; font-size: 1.2em;">ðŸŒ‹ Earthquake M${mag.toFixed(1)}</strong><br>
                <span style="color: #555;">${place}</span><br>
                <small>ðŸ“… ${timeStr}</small><br>
                <small>ðŸ“ ${lat.toFixed(3)}, ${lon.toFixed(3)}</small>
            </div>
        `;

        // Create 200km radius circle (but don't add to map yet - only on click/hover)
        const circle = L.circle([lat, lon], {
            radius: 200000, // 200km in meters
            color: '#e74c3c',
            fillColor: '#e74c3c',
            fillOpacity: 0.1,
            weight: 2,
            dashArray: '5, 5'
        });

        // Add marker
        const marker = L.marker([lat, lon], { icon })
            .addTo(map)
            .bindPopup(popupContent);

        // Show circle on click or hover
        marker.on('click', function () {
            if (!map.hasLayer(circle)) {
                circle.addTo(map);
            }
        });

        marker.on('mouseover', function () {
            if (!map.hasLayer(circle)) {
                circle.addTo(map);
            }
        });

        marker.on('mouseout', function () {
            // Keep circle visible on click, only hide on mouseout if not clicked
            // We'll track if it was clicked
            if (!marker._clicked) {
                if (map.hasLayer(circle)) {
                    map.removeLayer(circle);
                }
            }
        });

        // Track click state
        marker.on('click', function () {
            marker._clicked = true;
        });

        // Hide circle when popup closes
        marker.on('popupclose', function () {
            marker._clicked = false;
            if (map.hasLayer(circle)) {
                map.removeLayer(circle);
            }
        });

        console.log(`Added earthquake marker at [${lat}, ${lon}] with magnitude ${mag}`);

        // Store in a separate object for earthquakes
        if (!markers.earthquakes) {
            markers.earthquakes = [];
        }
        markers.earthquakes.push(marker);

        // Store circles separately for cleanup
        if (!markers.earthquakeCircles) {
            markers.earthquakeCircles = [];
        }
        markers.earthquakeCircles.push(circle);
    });

    console.log(`Total earthquake markers added: ${markers.earthquakes ? markers.earthquakes.length : 0}`);
}

function createStandaloneLegend() {
    const legendDiv = document.getElementById('map-legend');
    if (!legendDiv) return;

    const isDarkMode = document.body.classList.contains('dark-mode');
    const textColor = isDarkMode ? '#ecf0f1' : '#2c3e50';
    const bgColor = isDarkMode ? 'var(--bg-tertiary)' : 'var(--bg-tertiary)';

    legendDiv.innerHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; padding: 16px; background: ${bgColor}; border-radius: 8px;">
            <div>
                <h4 style="margin: 0 0 12px 0; color: ${textColor}; font-size: 0.9rem; font-weight: bold;">Station Markers</h4>
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    <div style="display: flex; align-items: center; gap: 8px; color: ${textColor}; font-size: 0.85rem;">
                        <span class="marker-triangle marker-gray" style="display: inline-block;"></span>
                        <span>Normal Station</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px; color: ${textColor}; font-size: 0.85rem;">
                        <span class="marker-triangle marker-eq-reliable" style="display: inline-block;"></span>
                        <span>Anomaly with EQ (Mâ‰¥5.0)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px; color: ${textColor}; font-size: 0.85rem;">
                        <span class="marker-triangle marker-eq-false" style="display: inline-block;"></span>
                        <span>False Alarm (No EQ)</span>
                    </div>
                </div>
            </div>
            <div>
                <h4 style="margin: 0 0 12px 0; color: ${textColor}; font-size: 0.9rem; font-weight: bold;">Earthquake Magnitude Scale</h4>
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    <div style="display: flex; align-items: center; gap: 8px; color: ${textColor}; font-size: 0.85rem;">
                        <span style="display: inline-block; width: 16px; height: 16px; background: #f1c40f; border-radius: 50%; border: 2px solid white;"></span>
                        <span>M 5.0-5.9 (Moderate)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px; color: ${textColor}; font-size: 0.85rem;">
                        <span style="display: inline-block; width: 16px; height: 16px; background: #e67e22; border-radius: 50%; border: 2px solid white;"></span>
                        <span>M 6.0-6.9 (Strong)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px; color: ${textColor}; font-size: 0.85rem;">
                        <span style="display: inline-block; width: 16px; height: 16px; background: #e74c3c; border-radius: 50%; border: 2px solid white;"></span>
                        <span>M 7.0-7.9 (Major)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px; color: ${textColor}; font-size: 0.85rem;">
                        <span style="display: inline-block; width: 16px; height: 16px; background: #c0392b; border-radius: 50%; border: 2px solid white;"></span>
                        <span>M 8.0+ (Great)</span>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Update legend when dark mode changes
    const observer = new MutationObserver(() => {
        createStandaloneLegend(); // Recreate legend with new colors
    });
    observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
}

async function renderDashboard(date = null) {
    console.log('renderDashboard called with date:', date);
    // The template already has the structure, we just need to update it
    // Show loading state
    const mapContainer = document.getElementById('map-container');
    if (mapContainer) {
        mapContainer.innerHTML = '<div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-primary);"><p>Loading map data...</p></div>';
    }

    let data;
    try {
        console.log('Loading data...');
        data = await loadData(date);
        console.log('Data loaded:', data ? 'Success' : 'Failed', data);

        if (!data) {
            const dateStr = date || selectedDate || 'selected date';
            console.warn('No data available for date:', dateStr);
            if (mapContainer) {
                mapContainer.innerHTML = `
                    <div class="no-data" style="text-align: center; padding: 40px; color: var(--text-primary);">
                        <h2 style="color: #e74c3c; margin-bottom: 20px;">âš ï¸ No Data Available</h2>
                        <p style="font-size: 1.1em; margin-bottom: 10px;">
                            No data is available for <strong>${dateStr}</strong> or any previous days (within 7 days).
                        </p>
                        <p style="color: var(--text-secondary); font-size: 0.9em;">
                            Please select a different date from the dropdown above.
                        </p>
                    </div>
                `;
            }
            return;
        }
    } catch (error) {
        console.error('Error in renderDashboard:', error);
        if (mapContainer) {
            mapContainer.innerHTML = `
                <div class="error" style="text-align: center; padding: 40px; color: #e74c3c;">
                    <h2 style="margin-bottom: 20px;">âŒ Error Loading Data</h2>
                    <p style="font-size: 1.1em; margin-bottom: 10px;">
                        ${error.message || 'Unknown error occurred'}
                    </p>
                    <p style="color: var(--text-secondary); font-size: 0.9em;">
                        Please check the browser console for details.
                    </p>
                </div>
            `;
        }
        return;
    }

    // Data was successfully loaded - continue with rendering
    // Remove any existing fallback notices first to prevent duplicates
    const existingNotices = document.querySelectorAll('.fallback-notice');
    existingNotices.forEach(notice => notice.remove());

    // Show notice if any stations are using fallback data
    if (data.station_dates) {
        const stationsUsingFallback = Object.entries(data.station_dates)
            .filter(([station, dateUsed]) => dateUsed !== data.selected_date)
            .map(([station, dateUsed]) => ({ station, dateUsed }));

        const stationsWithSelectedDate = Object.entries(data.station_dates)
            .filter(([station, dateUsed]) => dateUsed === data.selected_date)
            .map(([station]) => station);

        // Group fallback stations by the date they're using
        const fallbackByDate = {};
        stationsUsingFallback.forEach(({ station, dateUsed }) => {
            if (!fallbackByDate[dateUsed]) {
                fallbackByDate[dateUsed] = [];
            }
            fallbackByDate[dateUsed].push(station);
        });

        if (stationsUsingFallback.length > 0) {
            const notice = document.createElement('div');
            notice.className = 'fallback-notice';
            notice.style.cssText = 'background: rgba(243, 156, 18, 0.15); border-left: 4px solid #f39c12; padding: 16px 20px; margin: 15px 0; border-radius: 8px; color: var(--text-primary); font-size: 0.95rem;';

            let noticeHTML = `<div style="display: flex; align-items: flex-start; gap: 12px;">`;
            noticeHTML += `<div style="font-size: 1.5em;">â„¹ï¸</div>`;
            noticeHTML += `<div style="flex: 1;">`;
            noticeHTML += `<strong style="color: var(--accent-warning); display: block; margin-bottom: 8px;">Data Availability Notice</strong>`;
            noticeHTML += `<p style="margin: 8px 0;">`;
            noticeHTML += `<strong>${stationsWithSelectedDate.length}</strong> station(s) have data for <strong>${formatDateForSelector(data.selected_date)}</strong>. `;
            noticeHTML += `<strong>${stationsUsingFallback.length}</strong> station(s) are using previous day's data:`;
            noticeHTML += `</p>`;

            // List stations by fallback date
            Object.entries(fallbackByDate).forEach(([fallbackDate, stations]) => {
                const stationList = stations.length <= 8
                    ? stations.join(', ')
                    : `${stations.slice(0, 8).join(', ')} and ${stations.length - 8} more`;
                noticeHTML += `<div style="margin: 8px 0; padding-left: 16px; border-left: 2px solid rgba(243, 156, 18, 0.5);">`;
                noticeHTML += `<strong>${stations.length} station(s)</strong> using data from <strong>${formatDateForSelector(fallbackDate)}</strong>: `;
                noticeHTML += `<span style="color: #bdc3c7; font-size: 0.9em;">${stationList}</span>`;
                noticeHTML += `</div>`;
            });

            if (data.selected_date === new Date().toISOString().split('T')[0]) {
                noticeHTML += `<p style="margin-top: 12px; font-size: 0.9em; color: #bdc3c7; font-style: italic;">`;
                noticeHTML += `Note: This is normal if the nighttime window (20:00-04:00 local time) has not yet completed for these stations.`;
                noticeHTML += `</p>`;
            } else {
                noticeHTML += `<p style="margin-top: 12px; font-size: 0.9em; color: #bdc3c7; font-style: italic;">`;
                noticeHTML += `Note: EVT threshold calculation requires 7 days of data. Stations without data for the selected date are showing the most recent available data.`;
                noticeHTML += `</p>`;
            }

            noticeHTML += `</div></div>`;
            notice.innerHTML = noticeHTML;

            const container = document.querySelector('.container') || document.body;
            const mapSection = document.querySelector('.map-section');
            if (mapSection && mapSection.parentNode) {
                mapSection.parentNode.insertBefore(notice, mapSection);
            } else {
                container.insertBefore(notice, container.firstChild);
            }
        }
    }

    // Update date selector
    const dateSelector = document.getElementById('date-selector');
    if (dateSelector && data.available_dates) {
        dateSelector.innerHTML = '';
        data.available_dates.forEach(date => {
            const option = document.createElement('option');
            option.value = date;
            option.textContent = formatDateForSelector(date);
            if (date === data.selected_date || date === data.most_recent_date) {
                option.selected = true;
            }
            dateSelector.appendChild(option);
        });
    }

    // Load metadata - handle both array and object formats
    if (data.metadata) {
        if (Array.isArray(data.metadata)) {
            // Format: metadata is an array of objects with 'code' field
            data.metadata.forEach(station => {
                if (station.code) {
                    stationMetadata[station.code] = station;
                }
            });
        } else if (typeof data.metadata === 'object') {
            // Format: metadata is an object with station codes as keys
            Object.keys(data.metadata).forEach(code => {
                stationMetadata[code] = data.metadata[code];
            });
        }
    }

    allStations = data.stations || [];
    allStationsData = data.data || {};

    // Identify anomalous stations
    anomalousStations = [];
    let totalStations = 0;
    let anomalousCount = 0;
    let withEQ = 0;

    const stationDataMap = {};
    for (const station of allStations) {
        totalStations++;
        const stationData = allStationsData[station];
        const hasAnomaly = stationData && stationData.is_anomalous;

        if (hasAnomaly) {
            anomalousCount++;
            anomalousStations.push(station);
            // Load correlations for the selected date
            const eqCorrelations = await loadEarthquakeCorrelations(station, data.selected_date);
            // Filter by magnitude >= 5.0 for reliability
            const reliableCorrelations = eqCorrelations.filter(eq => parseFloat(eq.earthquake_magnitude || eq.magnitude || 0) >= 5.0);
            if (reliableCorrelations.length > 0) {
                withEQ++;
            }

            // Allow FP/Pending status entries to pass through to map
            let mapCorrelations = reliableCorrelations;
            const statusEntries = eqCorrelations.filter(eq => eq.status === 'FP' || eq.status === 'Pending');
            if (statusEntries.length > 0) {
                mapCorrelations = [...reliableCorrelations, ...statusEntries];
            }

            // Note: False positives are collected in the cumulative loop below (lines 983-1037)
            // to avoid double-counting when the same date is processed multiple times
            stationDataMap[station] = { stationData, eqCorrelations: mapCorrelations };
        } else {
            // Note: False negatives are collected in the cumulative loop below (lines 978-1032)
            // to avoid double-counting when the same date is processed multiple times
            const fn = await loadFalseNegatives(station, data.selected_date);
            stationDataMap[station] = { stationData: null, eqCorrelations: [], falseNegatives: fn };
        }
    }

    // For cumulative false positives/negatives since Nov 18, 2025
    const ANALYSIS_START_DATE = '2025-11-18';
    let falseAlarms = 0;
    let falseNegatives = 0;
    let latestFalsePositiveDate = null;
    let latestFalseNegativeDate = null;
    try {
        const [anomalyHistory, falseNegativeHistory] = await Promise.all([
            getAnomalyHistory(),
            getFalseNegativeHistory()
        ]);

        const anomalyEntries = Array.isArray(anomalyHistory?.entries) ? anomalyHistory.entries : [];
        const falseNegativeEntries = Array.isArray(falseNegativeHistory?.entries) ? falseNegativeHistory.entries : [];

        // Deduplicate false positives by station+date to fix inflated count
        const falsePositiveEntries = anomalyEntries.filter(entry => entry && entry.has_correlated_eq !== true);
        const uniqueFalsePositives = new Map();
        falsePositiveEntries.forEach(entry => {
            const key = `${entry.station}_${entry.date}`;
            if (!uniqueFalsePositives.has(key)) {
                uniqueFalsePositives.set(key, entry);
            }
        });
        falseAlarms = uniqueFalsePositives.size;  // Only count unique station+date combos

        if (uniqueFalsePositives.size > 0) {
            const sortedFP = Array.from(uniqueFalsePositives.values())
                .sort((a, b) => (b.date || '').localeCompare(a.date || ''));
            latestFalsePositiveDate = sortedFP[0]?.date || null;
        }

        falseNegatives = falseNegativeEntries.length;
        if (falseNegativeEntries.length > 0) {
            const sortedFN = [...falseNegativeEntries].sort((a, b) => {
                const aTime = (a.earthquake_time || a.date || '').toString();
                const bTime = (b.earthquake_time || b.date || '').toString();
                return bTime.localeCompare(aTime);
            });
            const latestFN = sortedFN[0];
            if (latestFN) {
                const fnTime = latestFN.earthquake_time || latestFN.date;
                latestFalseNegativeDate = typeof fnTime === 'string' ? fnTime.split('T')[0] : fnTime;
            }
        }
    } catch (historyError) {
        console.debug('Unable to load history files for cumulative metrics:', historyError);
    }

    // Load earthquake statistics for selected date only (no fallback)
    let eqStats = { global: 0, within200km: 0 };
    let eqDateUsed = data.selected_date;

    // Only try the selected date
    try {
        const statsResponse = await fetch(`data/earthquake_stats_${data.selected_date}.json`);
        if (statsResponse.ok) {
            const statsData = await statsResponse.json();
            eqStats = {
                global: statsData.global_count || statsData.global || 0,
                within200km: statsData.within_200km_count || statsData.within200km || 0
            };
            eqDateUsed = data.selected_date;
        }
    } catch (error) {
        console.debug('Could not load earthquake statistics for selected date:', error);
    }

    // Create summary stats boxes (like before, but better styled)
    const summaryStatsEl = document.getElementById('summary-stats');
    if (summaryStatsEl) {
        summaryStatsEl.innerHTML = `
            <div class="metric-card">
                <h3>Active Stations</h3>
                <div class="value">${totalStations}</div>
                <div class="label">Total stations monitored</div>
            </div>
            <div class="metric-card">
                <h3>Anomalies Detected</h3>
                <div class="value">${anomalousCount}</div>
                <div class="label">Polarization ratio anomalies</div>
            </div>
            <div class="metric-card">
                <h3>Events (24h)</h3>
                <div class="value">${eqStats.global}</div>
                <div class="label">ðŸŒ Global Mâ‰¥5.0</div>
                <div class="sub-label" style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
                    ${eqStats.within200km} within 200km of stations
                </div>
            </div>
            <div class="metric-card ${falseAlarms > 0 ? 'warning' : ''}">
                <h3>False Positives</h3>
                <div class="value">${falseAlarms}</div>
                <div class="label">Anomalies without EQ Mâ‰¥5.0</div>
                <div class="sub-label" style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
                    Since: ${formatDateForSelector(ANALYSIS_START_DATE)}${latestFalsePositiveDate ? `<br>Latest: ${formatDateForSelector(latestFalsePositiveDate)}` : ''}
                </div>
            </div>
            <div class="metric-card ${falseNegatives > 0 ? 'warning' : ''}">
                <h3>False Negatives</h3>
                <div class="value">${falseNegatives}</div>
                <div class="label">EQ Mâ‰¥5.0 without anomaly</div>
                <div class="sub-label" style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
                    Since: ${formatDateForSelector(ANALYSIS_START_DATE)}${latestFalseNegativeDate ? `<br>Latest: ${formatDateForSelector(latestFalseNegativeDate)}` : ''}
                </div>
            </div>
        `;
    }

    // Update timestamp will be handled in renderDashboard

    // Update station selector dropdown
    const stationSelector = document.getElementById('station-selector');
    if (stationSelector) {
        stationSelector.innerHTML = '<option value="">Select a station...</option>';

        // Add anomalous stations first
        anomalousStations.forEach(station => {
            const metadata = stationMetadata[station] || {};
            const stationData = allStationsData[station];
            const eqCorrelations = stationDataMap[station]?.eqCorrelations || [];
            const hasEQ = eqCorrelations.length > 0;
            const label = `${station} - ${metadata.name || station}${hasEQ ? ' ðŸŒ‹' : ' âš ï¸'}`;
            const option = document.createElement('option');
            option.value = station;
            option.textContent = label;
            if (anomalousStations.indexOf(station) === 0) {
                option.selected = true;
            }
            stationSelector.appendChild(option);
        });

        // Add other stations
        allStations.filter(s => !anomalousStations.includes(s)).forEach(station => {
            const metadata = stationMetadata[station] || {};
            const option = document.createElement('option');
            option.value = station;
            option.textContent = `${station} - ${metadata.name || station} (Normal)`;
            stationSelector.appendChild(option);
        });

        // Setup change handler if not already set
        if (!stationSelector.hasAttribute('data-handler-attached')) {
            stationSelector.setAttribute('data-handler-attached', 'true');
            stationSelector.addEventListener('change', async (e) => {
                const selectedStation = e.target.value;
                if (selectedStation) {
                    await renderStationPlot(selectedStation);
                } else {
                    const plotDiv = document.getElementById('selected-station-plot');
                    if (plotDiv) plotDiv.innerHTML = '';
                }
            });
        }

        // Load first anomalous station by default
        if (anomalousStations.length > 0 && !stationSelector.value) {
            stationSelector.value = anomalousStations[0];
            await renderStationPlot(anomalousStations[0]);
        }

        // Create analytics charts
        const normalStations = totalStations - anomalousCount;
        const detectionRate = anomalousCount > 0 ? Math.round((withEQ / anomalousCount) * 100) : 0;
        await createAnalyticsCharts(data, normalStations, withEQ, falseAlarms, detectionRate);
    }

    // Initialize map - wait a bit for DOM to be ready
    setTimeout(async () => {
        const mapEl = document.getElementById('map-container');
        if (!mapEl) {
            console.error('Map container not found');
            return;
        }

        // Clear any loading message
        mapEl.innerHTML = '';

        // Ensure container has dimensions
        if (mapEl.offsetHeight === 0) {
            console.warn('Map container has no height, setting minimum height');
            mapEl.style.minHeight = '600px';
        }

        try {
            console.log('Initializing map...');
            initMap();

            if (!map) {
                console.error('Map initialization failed');
                mapEl.innerHTML = '<div style="padding: 20px; color: #e74c3c;">Failed to initialize map</div>';
                return;
            }

            // Wait for map to be ready
            await new Promise(resolve => setTimeout(resolve, 500));

            console.log('Adding station markers...', allStations.length);
            // Add all station markers
            for (const station of allStations) {
                const mapData = stationDataMap[station] || { stationData: allStationsData[station], eqCorrelations: [], falseNegatives: [] };
                addStationToMap(station, mapData.stationData, mapData.eqCorrelations, data, mapData.falseNegatives);
            }

            console.log('Loading earthquakes...');
            // Add earthquake markers
            const recentEarthquakes = await loadRecentEarthquakes(data.selected_date);
            console.log('Loaded earthquakes for map:', recentEarthquakes.length, recentEarthquakes);
            addEarthquakeMarkers(recentEarthquakes);

            // Create standalone legend outside the map
            createStandaloneLegend();

            // Invalidate map size to ensure it renders correctly
            setTimeout(() => {
                if (map) {
                    map.invalidateSize();
                    console.log('Map size invalidated');
                }
            }, 100);
        } catch (error) {
            console.error('Error initializing map:', error);
            mapEl.innerHTML = `<div style="padding: 20px; color: #e74c3c;">Error loading map: ${error.message}<br><small>${error.stack}</small></div>`;
        }
    }, 500);

    // Setup mobile plot panel toggle
    const togglePlotBtn = document.getElementById('toggle-plot-panel');
    const plotPanelContent = document.getElementById('plot-panel-content');
    if (togglePlotBtn && plotPanelContent) {
        // On mobile, start collapsed (but allow user to expand)
        const isMobile = window.innerWidth <= 768;
        if (isMobile) {
            // Set initial collapsed state
            plotPanelContent.style.maxHeight = '0';
            plotPanelContent.style.opacity = '0';
            plotPanelContent.style.overflow = 'hidden';
            togglePlotBtn.textContent = 'â–²';
        }

        togglePlotBtn.addEventListener('click', () => {
            const isCollapsed = plotPanelContent.style.maxHeight === '0px' ||
                plotPanelContent.classList.contains('collapsed');

            if (isCollapsed) {
                // Expand
                plotPanelContent.style.maxHeight = plotPanelContent.scrollHeight + 'px';
                plotPanelContent.style.opacity = '1';
                plotPanelContent.classList.remove('collapsed');
                togglePlotBtn.textContent = 'â–¼';
            } else {
                // Collapse
                plotPanelContent.style.maxHeight = '0';
                plotPanelContent.style.opacity = '0';
                plotPanelContent.classList.add('collapsed');
                togglePlotBtn.textContent = 'â–²';
            }
        });

        // Handle window resize
        let resizeTimer;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => {
                const isMobileNow = window.innerWidth <= 768;
                if (!isMobileNow) {
                    // Desktop: always show
                    plotPanelContent.style.maxHeight = 'none';
                    plotPanelContent.style.opacity = '1';
                    plotPanelContent.classList.remove('collapsed');
                }
            }, 250);
        });
    }

    // Setup toggle button
    const toggleBtn = document.getElementById('toggle-stations');
    const stationsList = document.getElementById('stations-list');
    if (toggleBtn && stationsList) {
        toggleBtn.addEventListener('click', () => {
            stationsList.classList.toggle('hidden');
            toggleBtn.textContent = stationsList.classList.contains('hidden')
                ? 'ðŸ“‹ Show All Stations List'
                : 'ðŸ“‹ Hide Stations List';
            if (!stationsList.classList.contains('hidden')) {
                renderStationsList(allStations, allStationsData);
            }
        });
    }

    // Update Run Health / Data Availability
    const availableStationsCount = allStations.filter(s => allStationsData[s]).length;
    updateRunHealth(data, allStations.length, availableStationsCount);

    // Update timestamp (UTC-based)
    const timestampEl = document.getElementById('timestamp');
    if (timestampEl) {
        if (data.last_updated) {
            timestampEl.textContent = new Date(data.last_updated).toLocaleString('en-US', {
                timeZone: 'UTC',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                timeZoneName: 'short'
            });
        } else {
            // Fallback to current time in UTC
            timestampEl.textContent = new Date().toLocaleString('en-US', {
                timeZone: 'UTC',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                timeZoneName: 'short'
            });
        }
    }
}

async function renderStationPlot(stationCode) {
    const plotDiv = document.getElementById('selected-station-plot');
    if (!plotDiv) return;

    plotDiv.innerHTML = '<div class="loading">Loading station data...</div>';

    const stationData = allStationsData[stationCode];
    const metadata = stationMetadata[stationCode] || {};
    const eqCorrelations = await loadEarthquakeCorrelations(stationCode, selectedDate);
    // Filter by magnitude >= 5.0 for reliability
    const reliableCorrelations = eqCorrelations.filter(eq => parseFloat(eq.earthquake_magnitude || eq.magnitude || 0) >= 5.0);
    const hasEQ = reliableCorrelations.length > 0;
    const hasAnomaly = stationData && stationData.is_anomalous;
    const falseNegatives = await loadFalseNegatives(stationCode, selectedDate);

    // Get the date being used for this station
    const stationDateUsed = stationData?.date || selectedDate || mostRecentDate;
    const isUsingFallback = selectedDate && stationDateUsed !== selectedDate;

    let html = `<div class="station-plot-card">`;
    html += `<div class="plot-header">`;
    html += `<h3>${stationCode} - ${metadata.name || stationCode}</h3>`;
    html += `<p class="plot-location">${metadata.country || ''} | ðŸ“ ${metadata.latitude ? metadata.latitude.toFixed(3) : 'N/A'}, ${metadata.longitude ? metadata.longitude.toFixed(3) : 'N/A'}</p>`;

    // Show date indicator
    if (isUsingFallback && selectedDate) {
        html += `<div style="margin-top: 8px; padding: 8px 12px; background: rgba(243, 156, 18, 0.15); border-left: 3px solid #f39c12; border-radius: 4px; font-size: 0.9em; color: var(--accent-warning);">`;
        html += `ðŸ“… Showing data from <strong>${formatDate(stationDateUsed)}</strong> (selected: ${formatDateForSelector(selectedDate)})`;
        html += `</div>`;
    } else if (stationData) {
        html += `<div style="margin-top: 8px; padding: 8px 12px; background: rgba(149, 165, 166, 0.1); border-left: 3px solid #95a5a6; border-radius: 4px; font-size: 0.9em; color: var(--text-secondary);">`;
        html += `ðŸ“… Data from: <strong>${formatDate(stationDateUsed)}</strong>`;
        html += `</div>`;
    }

    if (hasAnomaly) {
        html += `<div class="plot-status ${hasEQ ? 'status-eq' : 'status-false'}">`;
        html += hasEQ ? `ðŸŒ‹ EQ Correlation Found (Mâ‰¥5.0): ${reliableCorrelations.length}` : `âš ï¸ False Alarm (No EQ Mâ‰¥5.0)`;
        html += `</div>`;
    } else {
        html += `<div class="plot-status status-normal">âœ… Normal</div>`;
        if (falseNegatives.length > 0) {
            html += `<div class="plot-status status-false-negative" style="margin-top: 8px;">âŒ False Negative: ${falseNegatives.length} EQ Mâ‰¥5.0 without anomaly</div>`;
        }
    }
    html += `</div>`;

    // Load and display figure
    // Use the date from stationData (which should match selectedDate)
    // This ensures the figure matches the data being displayed
    const plotDate = stationData?.date || selectedDate || mostRecentDate;
    console.log(`[renderStationPlot] Loading figure for ${stationCode} with date: ${plotDate} (stationData.date: ${stationData?.date}, selectedDate: ${selectedDate})`);
    const figures = await loadStationFigures(stationCode, plotDate);
    if (figures.length > 0) {
        html += `<div class="plot-image-container">`;
        html += `<img src="figures/${stationCode}/${figures[0]}" alt="PRA Plot for ${stationCode}" class="plot-image" onerror="this.parentElement.innerHTML='<p class=\\'error\\'>Plot not available</p>'">`;
        html += `</div>`;
    } else {
        html += `<div class="no-plot">Plot not available for this station</div>`;
    }

    // Add station info
    if (stationData) {
        html += `<div class="plot-info">`;
        html += `<div class="info-row"><span class="info-label">Date:</span><span class="info-value">${formatDate(stationData.date)}</span></div>`;
        html += `<div class="info-row"><span class="info-label">Threshold:</span><span class="info-value">${parseFloat(stationData.threshold || 0).toFixed(2)}</span> <span style="font-size: 0.8em; color: var(--text-secondary);">(EVT GPD, 7-day)</span></div>`;
        html += `<div class="info-row"><span class="info-label">Anomaly Hours:</span><span class="info-value">${stationData.nAnomHours || 0}</span></div>`;
        // Show reliable correlations (M>=5.0)
        if (hasEQ && reliableCorrelations.length > 0) {
            html += `<div class="eq-info">`;
            html += `<h4>ðŸŒ‹ Earthquake Correlations (Mâ‰¥5.0):</h4>`;
            reliableCorrelations.slice(0, 5).forEach((eq) => {
                const mag = eq.earthquake_magnitude || 'N/A';
                const dist = parseFloat(eq.earthquake_distance_km || 0).toFixed(1);
                const days = parseFloat(eq.days_before_anomaly || 0).toFixed(1);
                html += `<div class="eq-item">M${mag} @ ${dist}km (${days} days before)</div>`;
            });
            html += `</div>`;
        }

        // Show false negatives if any
        if (falseNegatives.length > 0) {
            html += `<div class="fn-info">`;
            html += `<h4>âŒ False Negatives (Mâ‰¥5.0, no anomaly detected):</h4>`;
            falseNegatives.slice(0, 3).forEach((fn) => {
                const mag = fn.earthquake_magnitude || 'N/A';
                const dist = parseFloat(fn.earthquake_distance_km || 0).toFixed(1);
                const date = fn.earthquake_time ? formatDate(fn.earthquake_time) : 'Unknown';
                html += `<div class="fn-item">M${mag} @ ${dist}km on ${date}</div>`;
            });
            if (falseNegatives.length > 3) {
                html += `<div class="fn-item">... and ${falseNegatives.length - 3} more</div>`;
            }
            html += `</div>`;
        }
        html += `</div>`;
    }

    html += `</div>`;
    plotDiv.innerHTML = html;
}

async function loadStationFigures(station, date = null) {
    // If date is provided, use it directly
    if (date) {
        const dateStr = date.replace(/-/g, '');
        const filename = `PRA_${station}_${dateStr}.png`;
        console.log(`[loadStationFigures] Using provided date for ${station}: ${date} -> ${filename}`);
        return [filename];
    }

    // Fallback: Try to get date from station data
    try {
        // Try to use selectedDate or mostRecentDate
        const useDate = selectedDate || mostRecentDate;
        if (useDate) {
            const dateStr = useDate.replace(/-/g, '');
            const filename = `PRA_${station}_${dateStr}.png`;
            console.log(`[loadStationFigures] Using selectedDate/mostRecentDate for ${station}: ${useDate} -> ${filename}`);
            return [filename];
        }

        // Last resort: Try to fetch from date-specific JSON file
        // Check available dates and try the most recent one
        if (availableDates && availableDates.length > 0) {
            console.log(`[loadStationFigures] Trying available dates for ${station}:`, availableDates);
            for (const availableDate of availableDates) {
                const dateStr = availableDate.replace(/-/g, '');
                const filename = `PRA_${station}_${dateStr}.png`;
                // Check if file exists by trying to load it
                try {
                    const testResponse = await fetch(`figures/${station}/${filename}`, { method: 'HEAD' });
                    if (testResponse.ok) {
                        console.log(`[loadStationFigures] Found plot file for ${station}: ${filename}`);
                        return [filename];
                    }
                } catch (e) {
                    // Continue to next date
                }
            }
        }
    } catch (e) {
        console.warn(`[loadStationFigures] Could not determine figure for station ${station}:`, e);
    }

    console.warn(`[loadStationFigures] No plot file found for station ${station}`);
    return [];
}

async function renderStationsList(stations, stationsData) {
    const listEl = document.getElementById('stations-list');
    if (!listEl) return;

    let html = '<table class="stations-table"><thead><tr>';
    html += '<th>Code</th><th>Name</th><th>Country</th><th>Status</th><th>ðŸŒ‹ EQ Correlation</th>';
    html += '</tr></thead><tbody>';

    for (const station of stations) {
        const metadata = stationMetadata[station] || {};
        const data = stationsData && stationsData[station];
        const hasAnomaly = data && data.is_anomalous;
        const eqCorrelations = await loadEarthquakeCorrelations(station, selectedDate);
        const hasEQ = eqCorrelations.length > 0;

        html += '<tr>';
        html += `<td><strong>${station}</strong></td>`;
        html += `<td>${metadata.name || station}</td>`;
        html += `<td>${metadata.country || '-'}</td>`;

        if (hasAnomaly) {
            html += `<td><span class="badge badge-danger">âš ï¸ Anomaly</span></td>`;
            html += `<td>${hasEQ ? '<span class="badge badge-eq">ðŸŒ‹ Yes (' + eqCorrelations.length + ')</span>' : '<span class="badge badge-warning">âš ï¸ No (False Alarm)</span>'}</td>`;
        } else {
            html += `<td><span class="badge badge-secondary">âœ… Normal</span></td>`;
            html += `<td>-</td>`;
        }

        html += '</tr>';
    }

    html += '</tbody></table>';
    listEl.innerHTML = html;
}


// Download anomalies CSV
async function downloadAnomaliesCSV() {
    try {
        // Collect all anomaly data from all stations using JSON data we already have
        const allAnomalies = [];

        // Use the data we already loaded in allStationsData
        for (const station of allStations) {
            try {
                const stationData = allStationsData[station];
                if (stationData && stationData.timestamps && stationData.isAnomalous) {
                    // Extract anomalies from the station data
                    for (let i = 0; i < stationData.timestamps.length; i++) {
                        if (stationData.isAnomalous[i]) {
                            const anomaly = {
                                Station: station,
                                TimeOfAnomaly: stationData.timestamps[i],
                                AnomalyValue: stationData.P ? stationData.P[i] : '',
                                nZ: stationData.nZ ? stationData.nZ[i] : '',
                                nG: stationData.nG ? stationData.nG[i] : '',
                                Threshold: stationData.threshold || ''
                            };
                            allAnomalies.push(anomaly);
                        }
                    }
                } else {
                    // Fallback: try to load from CSV if JSON doesn't have anomaly info
                    try {
                        const response = await fetch(`data/${station}_anomalies.csv`);
                        if (response.ok) {
                            const csvText = await response.text();
                            const anomalies = parseCSV(csvText);

                            // Add station code to each anomaly
                            anomalies.forEach(anomaly => {
                                anomaly.Station = station;
                                allAnomalies.push(anomaly);
                            });
                        }
                    } catch (error) {
                        // Silently ignore - CSV files are optional
                    }
                }
            } catch (error) {
                // Silently ignore errors for individual stations
            }
        }

        if (allAnomalies.length === 0) {
            alert('No anomalies found to download.');
            return;
        }

        // Convert to CSV format
        const headers = Object.keys(allAnomalies[0]);
        const csvRows = [
            headers.join(','),
            ...allAnomalies.map(row =>
                headers.map(header => {
                    const value = row[header] || '';
                    // Escape commas and quotes in CSV
                    if (typeof value === 'string' && (value.includes(',') || value.includes('"'))) {
                        return `"${value.replace(/"/g, '""')}"`;
                    }
                    return value;
                }).join(',')
            )
        ];

        const csvContent = csvRows.join('\n');
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);

        link.setAttribute('href', url);
        link.setAttribute('download', `anomalies_${selectedDate || new Date().toISOString().split('T')[0]}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        console.log(`Downloaded ${allAnomalies.length} anomalies`);
    } catch (error) {
        console.error('Error downloading anomalies CSV:', error);
        alert('Error downloading anomalies CSV. Please try again.');
    }
}

function updateRunHealth(data, totalStationsCount, loadedStationsCount) {
    const healthEl = document.getElementById('run-health');
    if (!healthEl) return;

    if (!data) {
        healthEl.style.display = 'none';
        return;
    }

    healthEl.style.display = 'block';

    // Calculate availability percentage
    const availabilityPct = totalStationsCount > 0 ? Math.round((loadedStationsCount / totalStationsCount) * 100) : 0;
    const isHybrid = data.is_hybrid_aggregation || false;

    let statusColor = 'var(--accent-success)';
    let statusIcon = 'âœ…';
    if (availabilityPct < 50) {
        statusColor = '#e74c3c';
        statusIcon = 'âš ï¸';
    } else if (availabilityPct < 90) {
        statusColor = '#f39c12';
        statusIcon = 'âš ï¸';
    }

    let html = `
        <h3>${statusIcon} Data Availability Report</h3>
        <div class="health-grid">
            <div class="health-item">
                <div class="health-label">Stations Available</div>
                <div class="health-value" style="color: ${statusColor}">${loadedStationsCount} / ${totalStationsCount}</div>
                <div class="health-meta">${availabilityPct}% Coverage</div>
            </div>
            <div class="health-item">
                <div class="health-label">Data Source</div>
                <div class="health-value">${isHybrid ? 'Hybrid' : 'Standard'}</div>
                <div class="health-meta">${isHybrid ? 'Partial data + Fallbacks' : 'Direct/Aggregated'}</div>
            </div>
            <div class="health-item">
                <div class="health-label">Processing Date</div>
                <div class="health-value">${formatDate(data.selected_date)}</div>
                <div class="health-meta">Analysis Window</div>
            </div>
        </div>
    `;

    // Add specific warnings if any
    if (isHybrid) {
        html += `
            <div class="alert alert-warning" style="margin-top: 10px; padding: 10px; background: rgba(243, 156, 18, 0.1); border-left: 4px solid #f39c12; border-radius: 4px;">
                <strong>Notice:</strong> Some stations are using fallback data from previous days due to missing data for the selected date.
            </div>
        `;
    }

    healthEl.innerHTML = html;
}
```

---

## deploy_all.ps1

```powershell
# Master Deployment Script - Complete Workflow
# This script runs the ENTIRE workflow in the correct order:
# 1. Process all stations (pra_nighttime.py)
# 2. Integrate earthquakes (integrate_earthquakes.py)
# 3. Prepare web output (upload_results.py)
# 4. Deploy to GitHub Pages (deploy_to_github.ps1)
#
# Usage: Just double-click this file or run: .\deploy_all.ps1

$ErrorActionPreference = "Continue"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

function Write-Log {
    param([string]$Message, [string]$Color = "White")
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$Timestamp] $Message" -ForegroundColor $Color
}

Write-Log "==========================================" "Cyan"
Write-Log "PRA Complete Deployment Workflow" "Cyan"
Write-Log "==========================================" "Cyan"
Write-Log ""

# Ensure we process ALL stations
if (Test-Path Env:INTERMAGNET_STATIONS) {
    Remove-Item Env:INTERMAGNET_STATIONS
    Write-Log "Note: INTERMAGNET_STATIONS was unset - processing ALL stations" "Yellow"
}

# Check if FORCE_RERUN is requested (from rerun_analysis.bat or manual setting)
if (Test-Path Env:FORCE_RERUN) {
    Write-Log "Note: FORCE_RERUN is enabled - will reprocess all stations" "Yellow"
} else {
    Write-Log "Note: Using cached results if available (set FORCE_RERUN=1 to force rerun)" "Gray"
}

# Detect Python with required packages (MUST be before first use)
$pythonExe = $null
if (Test-Path "C:\Users\SYAIFUL\anaconda3\python.exe") {
    $pythonExe = "C:\Users\SYAIFUL\anaconda3\python.exe"
} else {
    $pythonExe = "python"
}

# Preflight: make sure the latest raw data exists for every station
Write-Log ""
Write-Log "Preflight: Checking station data availability (today vs yesterday)..." "Yellow"
& $pythonExe ensure_station_data.py
if ($LASTEXITCODE -ne 0) {
    Write-Log "WARNING: Data availability pre-check encountered issues. Review logs above." "Yellow"
} else {
    Write-Log "Preflight check complete - raw data is up to date." "Green"
}
Write-Log ""

# Step 1: Run PRA Analysis
Write-Log "Step 1/4: Running PRA Analysis (pra_nighttime.py)..." "Yellow"
Write-Log "This may take several minutes for all stations..." "Gray"

& $pythonExe pra_nighttime.py
if ($LASTEXITCODE -ne 0) {
    Write-Log "ERROR: PRA analysis failed!" "Red"
    Write-Log "Please check the error messages above" "Red"
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Log "PRA analysis completed" "Green"
Write-Log ""

# Step 2: Integrate Earthquakes
Write-Log "Step 2/4: Integrating Earthquake Data (integrate_earthquakes.py)..." "Yellow"
& $pythonExe integrate_earthquakes.py
if ($LASTEXITCODE -ne 0) {
    Write-Log "WARNING: Earthquake integration had issues, but continuing..." "Yellow"
} else {
    Write-Log "Earthquake integration completed" "Green"
}
Write-Log ""

# Step 3: Prepare Web Output (CRITICAL - This regenerates stations.json with all stations)
Write-Log "Step 3/4: Preparing Web Output (upload_results.py)..." "Yellow"
Write-Log "This step is CRITICAL - it regenerates stations.json with all processed stations" "Cyan"

# Check for merge conflicts in upload_results.py and clean them if found
$uploadResultsPath = "upload_results.py"
if (Test-Path $uploadResultsPath) {
    $content = Get-Content $uploadResultsPath -Raw
    # Only match actual Git conflict markers (not just any line with = signs)
    if ($content -match "(?m)^[\s]*<<<<<<<|(?m)^[\s]*=======[\s]*$|(?m)^[\s]*>>>>>>>") {
        Write-Log "WARNING: Merge conflicts detected in upload_results.py! Cleaning automatically..." "Yellow"
        try {
            # Read the file line by line and remove conflict markers
            $lines = Get-Content $uploadResultsPath
            $cleanLines = @()
            $inConflict = $false
            $keepSection = $false
            
            foreach ($line in $lines) {
                if ($line -match "^<<<<<<<") {
                    $inConflict = $true
                    # If it says "Updated upstream", keep that section; otherwise keep first section by default
                    $keepSection = $line -match "Updated upstream"
                    if (-not $keepSection) {
                        # Default: keep first section (before =======)
                        $keepSection = $true
                    }
                    continue
                }
                if ($line -match "^=======") {
                    # If we're keeping the first section, skip everything until >>>>>>>
                    # If we're keeping the second section, start keeping lines now
                    if ($keepSection) {
                        # Skip the second section
                        continue
                    } else {
                        # Start keeping the second section
                        $keepSection = $true
                        continue
                    }
                }
                if ($line -match "^>>>>>>>") {
                    $inConflict = $false
                    $keepSection = $false
                    continue
                }
                
                # Add line if we're not in conflict, or if we're keeping this section
                if (-not $inConflict -or $keepSection) {
                    $cleanLines += $line
                }
            }
            
            # Write cleaned content
            $cleanLines | Set-Content -Path $uploadResultsPath
            Write-Log "Successfully cleaned merge conflicts in upload_results.py" "Green"
            
            # Post-cleanup: Remove duplicate code patterns that often result from merge conflicts
            # Read the file again to check for duplicates
            $finalLines = Get-Content $uploadResultsPath
            $deduplicatedLines = @()
            $previousLine = ""
            $skipNext = $false
            
            for ($i = 0; $i -lt $finalLines.Count; $i++) {
                $currentLine = $finalLines[$i]
                $trimmedCurrent = $currentLine.Trim()
                $trimmedPrevious = $previousLine.Trim()
                
                # Skip if this line is a duplicate of the previous line (common merge conflict artifact)
                # But only if both are similar if statements or similar code patterns
                if ($trimmedCurrent -ne "" -and $trimmedPrevious -ne "") {
                    # Check for duplicate if statements with similar conditions
                    if ($trimmedCurrent -match "^if\s+.*is_dir\(\)" -and $trimmedPrevious -match "^if\s+.*is_dir\(\)") {
                        # If current line is a subset of previous (shorter condition), skip it
                        if ($trimmedCurrent.Length -lt $trimmedPrevious.Length -and $trimmedPrevious.Contains($trimmedCurrent.Substring(0, [Math]::Min(30, $trimmedCurrent.Length)))) {
                            Write-Log "Removing duplicate if statement at line $($i+1)" "Yellow"
                            continue
                        }
                    }
                    
                    # Check for orphaned return statements after another return
                    if ($trimmedCurrent -match "^return\s+" -and $trimmedPrevious -match "^return\s+") {
                        # Check if there's a comment like "Last resort" before the second return
                        if ($i -gt 1 -and $finalLines[$i-2] -match "Last resort") {
                            Write-Log "Removing orphaned return statement at line $($i+1)" "Yellow"
                            continue
                        }
                    }
                }
                
                # Check for lines that are exactly the same (duplicate consecutive lines)
                if ($trimmedCurrent -eq $trimmedPrevious -and $trimmedCurrent -ne "" -and $trimmedCurrent -notmatch "^#") {
                    # Skip exact duplicates (but keep comments and blank lines)
                    continue
                }
                
                $deduplicatedLines += $currentLine
                $previousLine = $currentLine
            }
            
            # Write deduplicated content
            $deduplicatedLines | Set-Content -Path $uploadResultsPath
            Write-Log "Removed duplicate code patterns" "Green"
            
            # Verify it's clean (check for conflict markers)
            $verifyContent = Get-Content $uploadResultsPath -Raw
            if ($verifyContent -match "(?m)^[\s]*<<<<<<<|(?m)^[\s]*=======[\s]*$|(?m)^[\s]*>>>>>>>") {
                Write-Log "ERROR: Failed to clean all conflicts. Please resolve manually." "Red"
                exit 1
            }
            
            # Verify Python syntax is valid
            $syntaxCheck = & $pythonExe -m py_compile $uploadResultsPath 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Log "ERROR: Python syntax error after conflict cleanup!" "Red"
                Write-Log "Syntax error details: $syntaxCheck" "Red"
                Write-Log "Please fix upload_results.py manually" "Red"
                exit 1
            }
            Write-Log "Verified: Python syntax is valid after cleanup" "Green"
        } catch {
            Write-Log "ERROR: Failed to clean merge conflicts: $_" "Red"
            Write-Log "Please resolve merge conflicts manually in upload_results.py" "Red"
            exit 1
        }
    }
}

& $pythonExe upload_results.py
if ($LASTEXITCODE -ne 0) {
    Write-Log "ERROR: Web output preparation failed!" "Red"
    Write-Log "Please check the error messages above" "Red"
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Log "Web output prepared" "Green"

# Verify stations.json was created correctly
$stationsJson = "web_output\data\stations.json"
if (Test-Path $stationsJson) {
    try {
        $jsonContent = Get-Content $stationsJson | ConvertFrom-Json
        $stationCount = if ($jsonContent.stations) { $jsonContent.stations.Count } else { 0 }
        Write-Log "Verified: stations.json contains $stationCount stations" "Green"
        if ($stationCount -le 1) {
            Write-Log "WARNING: Only $stationCount station(s) found! This may indicate a problem." "Yellow"
            Write-Log "Check that pra_nighttime.py processed all stations successfully." "Yellow"
        }
    } catch {
        Write-Log "WARNING: Could not verify stations.json content" "Yellow"
    }
} else {
    Write-Log "ERROR: stations.json not found in web_output/data/" "Red"
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Log ""

# Step 4: Deploy to GitHub Pages (if configured)
$env:GITHUB_REPO = "syaifulafrizal/global-pra-observation"
$env:GITHUB_BRANCH = "gh-pages"

# Check for merge conflicts in deploy_to_github.ps1 and clean them if found
$deployScriptPath = "deploy_to_github.ps1"
if (Test-Path $deployScriptPath) {
    $content = Get-Content $deployScriptPath -Raw
    # Only match actual Git conflict markers (not just any line with = signs)
    # Pattern: <<<<<<< at start of line, or ======= at start (with optional spaces), or >>>>>>> at start
    if ($content -match "(?m)^[\s]*<<<<<<<|(?m)^[\s]*=======[\s]*$|(?m)^[\s]*>>>>>>>") {
        Write-Log "WARNING: Merge conflicts detected in deploy_to_github.ps1! Cleaning automatically..." "Yellow"
        try {
            # Read the file line by line and remove conflict markers
            $lines = Get-Content $deployScriptPath
            $cleanLines = @()
            $inConflict = $false
            $keepSection = $false
            
            foreach ($line in $lines) {
                if ($line -match "^<<<<<<<") {
                    $inConflict = $true
                    # If it says "Updated upstream", keep that section; otherwise keep first section by default
                    $keepSection = $line -match "Updated upstream"
                    if (-not $keepSection) {
                        # Default: keep first section (before =======)
                        $keepSection = $true
                    }
                    continue
                }
                if ($line -match "^=======") {
                    # If we're keeping the first section, skip everything until >>>>>>>
                    # If we're keeping the second section, start keeping lines now
                    if ($keepSection) {
                        # Skip the second section
                        continue
                    } else {
                        # Start keeping the second section
                        $keepSection = $true
                        continue
                    }
                }
                if ($line -match "^>>>>>>>") {
                    $inConflict = $false
                    $keepSection = $false
                    continue
                }
                
                # Add line if we're not in conflict, or if we're keeping this section
                if (-not $inConflict -or $keepSection) {
                    $cleanLines += $line
                }
            }
            
            # Write cleaned content
            $cleanLines | Set-Content -Path $deployScriptPath
            Write-Log "Successfully cleaned merge conflicts in deploy_to_github.ps1" "Green"
            
            # Verify PowerShell syntax is valid
            try {
                $null = [System.Management.Automation.PSParser]::Tokenize((Get-Content $deployScriptPath -Raw), [ref]$null)
                Write-Log "Verified: PowerShell syntax is valid after cleanup" "Green"
            } catch {
                Write-Log "ERROR: PowerShell syntax error after conflict cleanup!" "Red"
                Write-Log "Syntax error details: $_" "Red"
                Write-Log "Please fix deploy_to_github.ps1 manually" "Red"
                exit 1
            }
            
            # Verify it's clean - check multiple times with different patterns
            $verifyContent = Get-Content $deployScriptPath -Raw
            $verifyLines = Get-Content $deployScriptPath
            
            # Check for any remaining conflict markers (only actual Git markers, not code with = signs)
            $hasConflicts = $false
            foreach ($line in $verifyLines) {
                # Only match actual Git conflict markers at start of line
                if ($line -match "^[\s]*<<<<<<<|^[\s]*=======[\s]*$|^[\s]*>>>>>>>") {
                    $hasConflicts = $true
                    Write-Log "Found remaining conflict marker: $($line.Trim())" "Yellow"
                    break
                }
            }
            
            if ($hasConflicts) {
                # Try one more aggressive cleanup pass
                Write-Log "Attempting second cleanup pass..." "Yellow"
                $cleanLines2 = @()
                $inConflict2 = $false
                $keepSection2 = $true
                
                foreach ($line in $verifyLines) {
                    if ($line -match "^[\s]*<<<<<<<") {
                        $inConflict2 = $true
                        $keepSection2 = $line -match "Updated upstream"
                        if (-not $keepSection2) {
                            $keepSection2 = $true
                        }
                        continue
                    }
                    if ($line -match "^[\s]*=======") {
                        if ($keepSection2) {
                            continue
                        } else {
                            $keepSection2 = $true
                            continue
                        }
                    }
                    if ($line -match "^[\s]*>>>>>>>") {
                        $inConflict2 = $false
                        $keepSection2 = $false
                        continue
                    }
                    
                    if (-not $inConflict2 -or $keepSection2) {
                        $cleanLines2 += $line
                    }
                }
                
                $cleanLines2 | Set-Content -Path $deployScriptPath
                
                # Final verification (only check for actual Git conflict markers)
                $finalCheck = Get-Content $deployScriptPath -Raw
                if ($finalCheck -match "(?m)^[\s]*<<<<<<<|(?m)^[\s]*=======[\s]*$|(?m)^[\s]*>>>>>>>") {
                    Write-Log "ERROR: Failed to clean all conflicts after second pass. Please resolve manually." "Red"
                    Write-Log "You can manually edit deploy_to_github.ps1 and remove all lines containing: <<<<<<<, =======, >>>>>>>" "Yellow"
                    exit 1
                } else {
                    Write-Log "Successfully cleaned conflicts on second pass" "Green"
                }
            } else {
                Write-Log "Verification passed - file is clean" "Green"
            }
        } catch {
            Write-Log "ERROR: Failed to clean merge conflicts: $_" "Red"
            Write-Log "Please resolve merge conflicts manually in deploy_to_github.ps1" "Red"
            exit 1
        }
    }
}

if ($env:GITHUB_REPO) {
    Write-Log "Step 4/4: Deploying to GitHub Pages..." "Yellow"
    Write-Log "Repository: $env:GITHUB_REPO" "Gray"
    if ($env:GITHUB_BRANCH) {
        $branchName = $env:GITHUB_BRANCH
    } else {
        $branchName = "gh-pages"
    }
    Write-Log "Branch: $branchName" "Gray"
    Write-Log ""
    
    & ".\deploy_to_github.ps1"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Log "Deployment completed successfully!" "Green"
    } else {
        Write-Log "WARNING: Deployment had issues, but web output is ready locally" "Yellow"
    }
} else {
    Write-Log "Step 4/4: Skipping GitHub deployment (GITHUB_REPO not set)" "Yellow"
    Write-Log ""
    Write-Log "To enable GitHub Pages deployment:" "Cyan"
    Write-Log "  Set: `$env:GITHUB_REPO='username/repo-name'" "White"
    Write-Log "  Set: `$env:GITHUB_BRANCH='gh-pages'" "White"
    Write-Log ""
    Write-Log "Web output is ready in: web_output/" "Green"
    Write-Log "You can test locally with: python app.py" "Green"
}

Write-Log ""
Write-Log "==========================================" "Cyan"
Write-Log "Workflow Completed!" "Green"
Write-Log "==========================================" "Cyan"
Write-Log ""
Write-Log "Summary:" "Cyan"
Write-Log "  PRA analysis completed" "Green"
Write-Log "  Earthquake integration completed" "Green"
Write-Log "  Web output prepared" "Green"
if ($env:GITHUB_REPO) {
    Write-Log "  Deployed to GitHub Pages" "Green"
}
Write-Log ""

# Keep window open if run by double-clicking
if ($Host.Name -eq "ConsoleHost") {
    Write-Log "Press Enter to close this window..." "Gray"
    Read-Host
}
```

---

## deploy_to_github.ps1

```powershell
# Deploy Web Output to GitHub Pages
# This script pushes the web_output/ directory to GitHub for public hosting
# Designed to run after processing completes

$ErrorActionPreference = "Continue"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Configuration
$GITHUB_REPO = if ($env:GITHUB_REPO) { $env:GITHUB_REPO } else { "https://github.com/syaifulafrizal/global-pra-observation.git" }
$GITHUB_BRANCH = if ($env:GITHUB_BRANCH) { $env:GITHUB_BRANCH } else { "gh-pages" }
$GITHUB_TOKEN = $env:GITHUB_TOKEN

function Write-Log {
    param([string]$Message, [string]$Color = "White")
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$Timestamp] $Message" -ForegroundColor $Color
}

Write-Log "==========================================" "Cyan"
Write-Log "GitHub Pages Deployment" "Cyan"
Write-Log "==========================================" "Cyan"

# Check if web_output exists
if (-not (Test-Path "web_output")) {
    Write-Log "ERROR: web_output/ directory not found!" "Red"
    Write-Log "Run 'python upload_results.py' first to prepare files" "Yellow"
    exit 1
}

# Check if git is initialized
if (-not (Test-Path ".git")) {
    Write-Log "Initializing git repository..." "Yellow"
    git init
    git config user.name "PRA Automation" 2>$null
    git config user.email "pra@localhost" 2>$null
}

# Function to remove old data files
function Remove-OldDataFiles {
    param(
        [string]$DataDir,
        [datetime]$CutoffDate
    )
    
    $deletedCount = 0
    if (Test-Path $DataDir) {
        Get-ChildItem -Path $DataDir -Filter "*.json" | Where-Object {
            $_.LastWriteTime -lt $CutoffDate
        } | ForEach-Object {
            Write-Log "  Deleting old file: $($_.Name)" "Gray"
            Remove-Item $_.FullName -Force
            $deletedCount++
        }
        
        Get-ChildItem -Path $DataDir -Filter "*.png" | Where-Object {
            $_.LastWriteTime -lt $CutoffDate
        } | ForEach-Object {
            Write-Log "  Deleting old file: $($_.Name)" "Gray"
            Remove-Item $_.FullName -Force
            $deletedCount++
        }
    }
    return $deletedCount
}

# Configure remote - always ensure it's set correctly with full URL
$remotes = git remote 2>&1

# Normalize GITHUB_REPO to full URL format
$normalizedRepo = if ($GITHUB_REPO -match "^https://github\.com/") {
    # Already a full URL, ensure it ends with .git
    if ($GITHUB_REPO -notmatch "\.git$") {
        "$GITHUB_REPO.git"
    } else {
        $GITHUB_REPO
    }
} elseif ($GITHUB_REPO -match "^github\.com/") {
    # Missing https:// prefix
    "https://$GITHUB_REPO"
} elseif ($GITHUB_REPO -match "^[^/]+/[^/]+$") {
    # Just username/repo format
    "https://github.com/$GITHUB_REPO.git"
} else {
    # Assume it's already correct or use default
    $GITHUB_REPO
}

# Build expected URL (with token if provided)
$expectedUrl = if ($GITHUB_TOKEN) {
    if ($normalizedRepo -match "https://github\.com/(.+)") {
        $repoPath = $matches[1] -replace "\.git$", ""
        "https://$GITHUB_TOKEN@github.com/$repoPath.git"
    } else {
        $normalizedRepo
    }
} else {
    $normalizedRepo
}

Write-Log "Repository: $normalizedRepo" "White"
Write-Log "Branch: $GITHUB_BRANCH" "White"
Write-Log "" "White"

if ($remotes -notmatch "origin") {
    Write-Log "Adding remote origin..." "Yellow"
    git remote add origin $expectedUrl
} else {
    Write-Log "Updating remote origin URL..." "Yellow"
    git remote set-url origin $expectedUrl
    # Verify it was set correctly
    $verifyUrl = git remote get-url origin 2>&1
    if ($verifyUrl -ne $expectedUrl -and -not ($verifyUrl -match "error")) {
        Write-Log "Warning: Remote URL mismatch. Setting again..." "Yellow"
        git remote set-url origin $expectedUrl --push
        git remote set-url origin $expectedUrl
    }
    Write-Log "Remote URL verified: $expectedUrl" "Gray"
}

# Save current branch
$currentBranch = git rev-parse --abbrev-ref HEAD

# Step 1: Commit and push main branch changes first (if on main)
if ($currentBranch -eq "main" -or $currentBranch -eq "master") {
    Write-Log "Checking for uncommitted changes on $currentBranch branch..." "Yellow"
    $status = git status --porcelain
    if ($status) {
        Write-Log "Found uncommitted changes on $currentBranch, committing..." "Yellow"
        
        # Stage all changes (except web_output which is in .gitignore)
        git add -A 2>&1 | Out-Null
        git reset HEAD web_output/ 2>&1 | Out-Null  # Don't commit web_output to main
        
        $mainCommitMsg = "Update source files - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        git commit -m $mainCommitMsg 2>&1 | Out-Null
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Pushing $currentBranch branch to origin..." "Yellow"
            git push origin $currentBranch 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Log "Successfully pushed $currentBranch branch" "Green"
            } else {
                Write-Log "Warning: Failed to push $currentBranch (continuing with deployment)" "Yellow"
            }
        }
    }
}

# Save current branch
$currentBranch = git rev-parse --abbrev-ref HEAD

# Fetch latest from remote
Write-Log "Fetching latest from remote..." "Yellow"
git fetch origin 2>&1 | Out-Null

# IMPORTANT: Copy web_output to temp location BEFORE switching branches
# web_output is in .gitignore, so it won't exist on gh-pages branch
Write-Log "Preparing web_output for deployment..." "Yellow"
if (-not (Test-Path "web_output")) {
    Write-Log "ERROR: web_output/ directory not found on current branch!" "Red"
    Write-Log "Please run 'python upload_results.py' first to prepare files" "Red"
    exit 1
}

# Verify web_output/data/stations.json has correct format
if (Test-Path "web_output/data/stations.json") {
    try {
        $webOutputJson = Get-Content "web_output/data/stations.json" | ConvertFrom-Json
        $webOutputCount = if ($webOutputJson.stations) { $webOutputJson.stations.Count } else { 0 }
        $webOutputHasDates = $webOutputJson.available_dates -ne $null
        
        Write-Log "web_output verification:" "Yellow"
        Write-Log "  Stations: $webOutputCount" "Gray"
        Write-Log "  Has available_dates: $webOutputHasDates" "Gray"
        
        if ($webOutputCount -le 1 -or -not $webOutputHasDates) {
            Write-Log "ERROR: web_output/data/stations.json has wrong format!" "Red"
            Write-Log "Please run 'python upload_results.py' again to regenerate it" "Red"
            exit 1
        } else {
            Write-Log "Verified: web_output is correct ($webOutputCount stations)" "Green"
        }
    } catch {
        Write-Log "ERROR: Could not verify web_output/data/stations.json: $_" "Red"
        exit 1
    }
} else {
    Write-Log "ERROR: web_output/data/stations.json not found!" "Red"
    Write-Log "Please run 'python upload_results.py' first" "Red"
    exit 1
}

# Copy web_output to temp location (outside .gitignore) so it persists across branch switches
# Use absolute path in parent directory to ensure it persists across branch switches
$repoRoot = (Get-Location).Path
$parentDir = Split-Path -Parent $repoRoot
$tempWebOutput = Join-Path $parentDir "web_output_temp_deploy_$(Split-Path -Leaf $repoRoot)"
$tempStationsJson = Join-Path $parentDir "stations_json_temp_$(Split-Path -Leaf $repoRoot).json"

Write-Log "Copying web_output to temp location for branch switching..." "Yellow"
Write-Log "  Temp location: $tempWebOutput" "Gray"
Write-Log "  Temp stations.json: $tempStationsJson" "Gray"

if (Test-Path $tempWebOutput) {
    Remove-Item $tempWebOutput -Recurse -Force
}
Copy-Item -Path "web_output" -Destination $tempWebOutput -Recurse -Force

# Also copy stations.json to a single file that will persist (not in a directory)
if (Test-Path "web_output/data/stations.json") {
    Copy-Item -Path "web_output/data/stations.json" -Destination $tempStationsJson -Force
    Write-Log "Copied stations.json to temp file (will persist across branch switch)" "Green"
}

Write-Log "web_output copied to temp location (will be used after branch switch)" "Green"

# Push to GitHub
Write-Log "Deploying to GitHub Pages..." "Yellow"
try {
    if ($GITHUB_BRANCH -eq "gh-pages") {
        # Check if remote branch exists
        $remoteBranchExists = git branch -r | Select-String -Pattern "origin/gh-pages"
        $localBranchExists = git branch | Select-String -Pattern "^\s*gh-pages$"
        
        if (-not $remoteBranchExists) {
            # Create orphan branch for gh-pages (first time only)
            Write-Log "Creating gh-pages branch..." "Yellow"
            
            # Stash any uncommitted changes
            $hasChanges = git status --porcelain
            if ($hasChanges) {
                Write-Log "Stashing uncommitted changes..." "Yellow"
                git stash push -m "Auto-stash before gh-pages deployment" 2>&1 | Out-Null
            }
            
            git checkout --orphan gh-pages 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to create gh-pages branch"
            }
            git rm -rf --cached . 2>&1 | Out-Null
            
            # Copy web_output contents to root (GitHub Pages needs files at root)
            Write-Log "Copying web_output files to root..." "Yellow"
            if (Test-Path "web_output") {
                Copy-Item -Path "web_output\*" -Destination . -Recurse -Force
            }
            
            git add -f . 2>&1 | Out-Null
            git commit -m "Initial gh-pages commit" 2>&1 | Out-Null
        } else {
            Write-Log "Switching to gh-pages branch..." "Yellow"
            
            # Stash any uncommitted changes before switching
            $hasChanges = git status --porcelain
            if ($hasChanges) {
                Write-Log "Stashing uncommitted changes..." "Yellow"
                git stash push -m "Auto-stash before gh-pages deployment" 2>&1 | Out-Null
            }
            
            # Try to checkout existing local branch
            if ($localBranchExists) {
                git checkout gh-pages 2>&1 | Out-Null
            } else {
                # Create local branch tracking remote
                git checkout -b gh-pages origin/gh-pages 2>&1 | Out-Null
            }
            
            if ($LASTEXITCODE -ne 0) {
                # Force checkout by resetting the branch
                Write-Log "Force resetting gh-pages branch..." "Yellow"
                if ($localBranchExists) {
                    git branch -D gh-pages 2>&1 | Out-Null
                }
                git checkout -b gh-pages origin/gh-pages 2>&1 | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    throw "Failed to checkout gh-pages branch"
                }
            }
            
            # Verify we're on gh-pages
            $checkBranch = git rev-parse --abbrev-ref HEAD
            if ($checkBranch -ne "gh-pages") {
                throw "Not on gh-pages branch! Current: $checkBranch"
            }
            
            # Pull latest from remote to ensure we're up to date
            Write-Log "Pulling latest from origin/gh-pages..." "Yellow"
            git pull origin gh-pages 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Log "Warning: Failed to pull from remote (continuing anyway)" "Yellow"
            }
            
            # Copy web_output contents to root
            Write-Log "Copying web_output files to root..." "Yellow"
            # Remove existing files (except .git and web_output) - be more aggressive
            Write-Log "Removing old files from root..." "Yellow"
            Get-ChildItem -Path . -Exclude ".git", "web_output" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
            
            # Also remove any old index.html or static/ directory that might exist
            if (Test-Path "index.html") {
                Remove-Item "index.html" -Force -ErrorAction SilentlyContinue
            }
            if (Test-Path "static") {
                Remove-Item "static" -Recurse -Force -ErrorAction SilentlyContinue
            }
            if (Test-Path "data") {
                Remove-Item "data" -Recurse -Force -ErrorAction SilentlyContinue
            }
            if (Test-Path "figures") {
                Remove-Item "figures" -Recurse -Force -ErrorAction SilentlyContinue
            }
            
            # Copy from temp web_output location (web_output doesn't exist on gh-pages branch)
            # Use absolute path in parent directory (persists across branch switches)
            $repoRoot = (Get-Location).Path
            $parentDir = Split-Path -Parent $repoRoot
            $tempWebOutput = Join-Path $parentDir "web_output_temp_deploy_$(Split-Path -Leaf $repoRoot)"
            $tempStationsJson = Join-Path $parentDir "stations_json_temp_$(Split-Path -Leaf $repoRoot).json"
            
            Write-Log "Looking for temp files..." "Yellow"
            Write-Log "  Temp location: $tempWebOutput" "Gray"
            Write-Log "  Temp stations.json: $tempStationsJson" "Gray"
            
            # First, try to restore stations.json from the temp file (most reliable)
            if (Test-Path $tempStationsJson) {
                Write-Log "Found temp stations.json file, will use it after copying..." "Green"
            } else {
                Write-Log "Temp stations.json not found at: $tempStationsJson" "Yellow"
            }
            
            if (Test-Path $tempWebOutput) {
                Write-Log "Copying files from temp web_output to root..." "Yellow"
                # Copy all contents of temp web_output to current directory
                $webOutputPath = Resolve-Path $tempWebOutput
                Get-ChildItem -Path $webOutputPath -Force | ForEach-Object {
                    $destPath = Join-Path (Get-Location) $_.Name
                    if ($_.PSIsContainer) {
                        Copy-Item -Path $_.FullName -Destination $destPath -Recurse -Force
                    } else {
                        Copy-Item -Path $_.FullName -Destination $destPath -Force
                    }
                }
                Write-Log "Files copied successfully from temp location" "Green"
                
                # Overwrite stations.json with the temp file if it exists (ensures correct format)
                if (Test-Path $tempStationsJson) {
                    if (Test-Path "data/stations.json") {
                        Copy-Item -Path $tempStationsJson -Destination "data/stations.json" -Force
                        Write-Log "Overwrote stations.json with temp file (ensuring correct format)" "Green"
                    } else {
                        # Create data directory if it doesn't exist
                        if (-not (Test-Path "data")) {
                            New-Item -Path "data" -ItemType Directory -Force | Out-Null
                        }
                        Copy-Item -Path $tempStationsJson -Destination "data/stations.json" -Force
                        Write-Log "Created data/stations.json from temp file" "Green"
                    }
                }
            } elseif (Test-Path "web_output") {
                # Fallback: try web_output if temp doesn't exist
                Write-Log "Temp web_output not found, trying web_output directory..." "Yellow"
                $webOutputPath = Resolve-Path "web_output"
                Get-ChildItem -Path $webOutputPath -Force | ForEach-Object {
                    $destPath = Join-Path (Get-Location) $_.Name
                    if ($_.PSIsContainer) {
                        Copy-Item -Path $_.FullName -Destination $destPath -Recurse -Force
                    } else {
                        Copy-Item -Path $_.FullName -Destination $destPath -Force
                    }
                }
                Write-Log "Files copied successfully" "Green"
                
                # Also try to use temp stations.json if available
                if (Test-Path $tempStationsJson) {
                    if (Test-Path "data/stations.json") {
                        Copy-Item -Path $tempStationsJson -Destination "data/stations.json" -Force
                        Write-Log "Overwrote stations.json with temp file" "Green"
                    }
                }
            } else {
                throw "Neither temp web_output nor web_output directory found"
            }
            
            # Verify critical files exist and have correct content
            $criticalFiles = @('index.html', 'static/app.js', 'static/style.css', 'data/stations.json')
            $missingFiles = @()
            foreach ($file in $criticalFiles) {
                if (-not (Test-Path $file)) {
                    $missingFiles += $file
                }
            }
            if ($missingFiles.Count -gt 0) {
                Write-Log "ERROR: Missing critical files after copy: $($missingFiles -join ', ')" "Red"
                throw "Critical files missing after copy"
            } else {
                Write-Log "Verified: All critical files are present" "Green"
            }
            
            # Verify stations.json has correct format (not old format)
            try {
                $stationsJson = Get-Content "data/stations.json" | ConvertFrom-Json
                $stationCount = if ($stationsJson.stations) { $stationsJson.stations.Count } else { 0 }
                $hasAvailableDates = $stationsJson.available_dates -ne $null
                $hasMetadata = $stationsJson.metadata -ne $null
                
                Write-Log "Verifying stations.json content..." "Yellow"
                Write-Log "  Stations: $stationCount" "Gray"
                Write-Log "  Has available_dates: $hasAvailableDates" "Gray"
                Write-Log "  Has metadata: $hasMetadata" "Gray"
                
                if ($stationCount -le 1 -or -not $hasAvailableDates) {
                    Write-Log "ERROR: stations.json has old format! (Stations: $stationCount, Has dates: $hasAvailableDates)" "Red"
                    Write-Log "This suggests web_output/data/stations.json wasn't copied correctly" "Red"
                    Write-Log "Note: web_output may not exist on gh-pages branch (it's in .gitignore)" "Yellow"
                    Write-Log "Re-copying from temp stations.json file..." "Yellow"
                    
                    # Try temp stations.json file first (most reliable)
                    # Use absolute path in parent directory
                    $repoRoot = (Get-Location).Path
                    $parentDir = Split-Path -Parent $repoRoot
                    $tempStationsJson = Join-Path $parentDir "stations_json_temp_$(Split-Path -Leaf $repoRoot).json"
                    if (Test-Path $tempStationsJson) {
                        $webOutputJson = Get-Content $tempStationsJson | ConvertFrom-Json
                        $webOutputCount = if ($webOutputJson.stations) { $webOutputJson.stations.Count } else { 0 }
                        Write-Log "  temp stations.json has $webOutputCount stations" "Yellow"
                        if ($webOutputCount -gt 1) {
                            Copy-Item -Path $tempStationsJson -Destination "data/stations.json" -Force
                            Write-Log "Re-copied stations.json from temp file" "Green"
                        } else {
                            throw "temp stations.json also has wrong format ($webOutputCount stations)"
                        }
                    } else {
                        # Fallback: try temp web_output directory
                        $repoRoot = (Get-Location).Path
                        $parentDir = Split-Path -Parent $repoRoot
                        $tempWebOutput = Join-Path $parentDir "web_output_temp_deploy_$(Split-Path -Leaf $repoRoot)"
                        if (Test-Path "$tempWebOutput/data/stations.json") {
                            $webOutputJson = Get-Content "$tempWebOutput/data/stations.json" | ConvertFrom-Json
                            $webOutputCount = if ($webOutputJson.stations) { $webOutputJson.stations.Count } else { 0 }
                            Write-Log "  temp web_output has $webOutputCount stations" "Yellow"
                            if ($webOutputCount -gt 1) {
                                Copy-Item -Path "$tempWebOutput/data/stations.json" -Destination "data/stations.json" -Force
                                Write-Log "Re-copied stations.json from temp web_output" "Green"
                            } else {
                                throw "temp web_output also has wrong format ($webOutputCount stations)"
                            }
                        } else {
                            throw "Neither temp stations.json nor temp web_output found - cannot fix"
                        }
                    }
                } else {
                    Write-Log "Verified: stations.json has correct format ($stationCount stations)" "Green"
                }
            } catch {
                Write-Log "WARNING: Could not verify stations.json content: $_" "Yellow"
            }
            
            # Create/update .gitignore to exclude web_output directory
            if (-not (Test-Path ".gitignore")) {
                New-Item -Path ".gitignore" -ItemType File -Force | Out-Null
            }
            $gitignoreContent = Get-Content ".gitignore" -ErrorAction SilentlyContinue
            if ($gitignoreContent -notcontains "web_output/") {
                Add-Content -Path ".gitignore" -Value "web_output/"
            }
            
            # Clean up old files (older than 6 days)
            $cutoffDate = (Get-Date).AddDays(-6).Date
            $dataDir = Join-Path (Get-Location) "data"
            if (Test-Path $dataDir) {
                Write-Log "Cleaning up old data files (keeping last 7 days)..." "Yellow"
                Remove-OldDataFiles -DataDir $dataDir -CutoffDate $cutoffDate
            }
        }
        
        # Verify we're still on gh-pages before committing
        $verifyBranch = git rev-parse --abbrev-ref HEAD
        if ($verifyBranch -ne "gh-pages") {
            Write-Log "ERROR: Not on gh-pages branch! Current: $verifyBranch" "Red"
            throw "Branch mismatch detected"
        }
        
        # Stage all files at root (excluding web_output directory itself)
        Write-Log "Staging files..." "Yellow"
        # Stage .gitignore first to ensure web_output is ignored
        if (Test-Path ".gitignore") {
            git add -f .gitignore 2>&1 | Out-Null
        }
        # Use git add with . to add all files, then unstage web_output if it exists
        git add -f . 2>&1 | Out-Null
        # Remove web_output from staging (we don't want the folder, just its contents at root)
        git reset HEAD web_output/ 2>&1 | Out-Null
        
        # Verify critical files are staged and have correct content
        $stagedFiles = git diff --cached --name-only
        $criticalFiles = @('index.html', 'data/stations.json', 'static/app.js', 'static/style.css')
        $missingFiles = @()
        foreach ($file in $criticalFiles) {
            if (-not ($stagedFiles -contains $file)) {
                $missingFiles += $file
            }
        }
        if ($missingFiles.Count -gt 0) {
            Write-Log "WARNING: Missing critical files in staging: $($missingFiles -join ', ')" "Yellow"
            Write-Log "Attempting to stage missing files..." "Yellow"
            foreach ($file in $missingFiles) {
                if (Test-Path $file) {
                    git add -f $file 2>&1 | Out-Null
                    Write-Log "  Staged: $file" "Green"
                } else {
                    Write-Log "  ERROR: $file does not exist!" "Red"
                }
            }
        } else {
            Write-Log "All critical files are staged" "Green"
        }
        
        # Final verification: Check that staged stations.json has correct format
        if (Test-Path "data/stations.json") {
            try {
                $stagedJson = Get-Content "data/stations.json" | ConvertFrom-Json
                $stagedCount = if ($stagedJson.stations) { $stagedJson.stations.Count } else { 0 }
                $stagedHasDates = $stagedJson.available_dates -ne $null
                
                if ($stagedCount -le 1 -or -not $stagedHasDates) {
                    Write-Log "ERROR: Staged stations.json still has old format! ($stagedCount stations, dates: $stagedHasDates)" "Red"
                    Write-Log "Re-copying from temp stations.json file..." "Yellow"
                    # Use absolute path in parent directory
                    $repoRoot = (Get-Location).Path
                    $parentDir = Split-Path -Parent $repoRoot
                    $tempStationsJson = Join-Path $parentDir "stations_json_temp_$(Split-Path -Leaf $repoRoot).json"
                    if (Test-Path $tempStationsJson) {
                        Copy-Item -Path $tempStationsJson -Destination "data/stations.json" -Force
                        git add -f "data/stations.json" 2>&1 | Out-Null
                        Write-Log "Re-copied and re-staged stations.json from temp file" "Green"
                    } elseif (Test-Path "web_output/data/stations.json") {
                        Copy-Item -Path "web_output/data/stations.json" -Destination "data/stations.json" -Force
                        git add -f "data/stations.json" 2>&1 | Out-Null
                        Write-Log "Re-copied and re-staged stations.json from web_output" "Green"
                    } else {
                        throw "Cannot fix: Neither temp stations.json nor web_output/data/stations.json found"
                    }
                } else {
                    Write-Log "Final verification: Staged stations.json is correct ($stagedCount stations)" "Green"
                }
            } catch {
                Write-Log "WARNING: Could not verify staged stations.json: $_" "Yellow"
            }
        }
        
    } else {
        git checkout $GITHUB_BRANCH 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to checkout $GITHUB_BRANCH branch"
        }
        # For non-gh-pages branches, just add web_output as-is
        git add -f web_output/ 2>&1 | Out-Null
    }
    
    # Ensure git user is configured
    $gitUser = git config user.name 2>&1
    $gitEmail = git config user.email 2>&1
    if (-not $gitUser -or $gitUser -match "error") {
        Write-Log "Configuring git user..." "Yellow"
        git config user.name "PRA Automation" 2>&1 | Out-Null
        git config user.email "pra@localhost" 2>&1 | Out-Null
    }
    if (-not $gitEmail -or $gitEmail -match "error") {
        git config user.email "pra@localhost" 2>&1 | Out-Null
    }
    
    # Check if there are changes
    $status = git status --porcelain
    $hasChanges = $status -and ($status.Trim().Length -gt 0)
    
    # Commit changes (or create empty commit if no changes)
    $commitMessage = "Update web output - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    
    # Final verification of branch before commit
    $finalBranch = git rev-parse --abbrev-ref HEAD
    Write-Log "Committing on branch: $finalBranch" "Cyan"
    
    if ($hasChanges) {
        Write-Log "Committing changes..." "Yellow"
        $commitOutput = git commit -m $commitMessage 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log "Commit output: $commitOutput" "Red"
            Write-Log "Checking git status..." "Yellow"
            git status 2>&1 | Write-Host
            throw "Failed to commit changes. Exit code: $LASTEXITCODE"
        }
        Write-Log "Commit successful" "Green"
    } else {
        Write-Log "No file changes detected, creating empty commit to update timestamp..." "Yellow"
        $commitOutput = git commit --allow-empty -m $commitMessage 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log "Commit output: $commitOutput" "Red"
            throw "Failed to create empty commit. Exit code: $LASTEXITCODE"
        }
        Write-Log "Empty commit created successfully" "Green"
    }
    
    Write-Log "Pushing to origin/$GITHUB_BRANCH..." "Yellow"
    # Force push to ensure old files are overwritten and cache is cleared
    Write-Log "Using force push to overwrite any cached content..." "Yellow"
    $pushOutput = git push -u origin $GITHUB_BRANCH --force 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Push output: $pushOutput" "Red"
        # Check if it's a remote URL issue
        if ($pushOutput -match "does not appear to be a git repository") {
            Write-Log "ERROR: Remote URL is incorrect. Current remote:" "Red"
            git remote -v 2>&1 | Write-Host
            Write-Log "Attempting to fix remote URL..." "Yellow"
            # Always use the normalized full URL
            git remote set-url origin $expectedUrl
            Write-Log "Remote URL fixed to: $expectedUrl" "Yellow"
            Write-Log "Retrying push..." "Yellow"
            $pushOutput = git push -u origin $GITHUB_BRANCH --force 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to push to GitHub after fixing remote URL"
            }
        } else {
            throw "Failed to push to GitHub"
        }
    }
    
    # Clean up temp files before success message
    # Use absolute path in parent directory
    $repoRoot = (Get-Location).Path
    $parentDir = Split-Path -Parent $repoRoot
    $tempWebOutput = Join-Path $parentDir "web_output_temp_deploy_$(Split-Path -Leaf $repoRoot)"
    $tempStationsJson = Join-Path $parentDir "stations_json_temp_$(Split-Path -Leaf $repoRoot).json"
    if (Test-Path $tempWebOutput) {
        Write-Log "Cleaning up temp web_output directory..." "Yellow"
        Remove-Item $tempWebOutput -Recurse -Force -ErrorAction SilentlyContinue
        Write-Log "Temp directory cleaned up" "Green"
    }
    if (Test-Path $tempStationsJson) {
        Write-Log "Cleaning up temp stations.json file..." "Yellow"
        Remove-Item $tempStationsJson -Force -ErrorAction SilentlyContinue
        Write-Log "Temp file cleaned up" "Green"
    }
    
    Write-Log "SUCCESS: Deployed to GitHub!" "Green"
    Write-Log "" "White"
    Write-Log "Your site will be available at:" "Cyan"
    if ($GITHUB_REPO -match "github.com/(.+)") {
        $repoPath = $matches[1] -replace "\.git$", ""
    } else {
        $repoPath = $GITHUB_REPO -replace "\.git$", "" -replace "https://github.com/", ""
    }
    # Format: username/repo -> https://username.github.io/repo
    $parts = $repoPath -split "/"
    if ($parts.Length -eq 2) {
        $username = $parts[0]
        $repoName = $parts[1]
        $siteUrl = "https://$username.github.io/$repoName"
        Write-Log "  $siteUrl" "Green"
    } else {
        $siteUrl = "https://$repoPath.github.io"
        Write-Log "  $siteUrl" "Green"
    }
    Write-Log "" "White"
    Write-Log "Deployment Notes:" "Cyan"
    Write-Log "  - GitHub Pages may take 1-2 minutes to update" "Yellow"
    Write-Log "  - If you see the old version, clear your browser cache:" "Yellow"
    Write-Log "    * Press Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)" "White"
    Write-Log "    * Or open in an incognito/private window" "White"
    Write-Log "  - The deployment includes today's data: $(Get-Date -Format 'yyyy-MM-dd')" "Green"
    Write-Log "" "White"
    
    # Switch back to original branch
    if ($currentBranch -and $currentBranch -ne $GITHUB_BRANCH) {
        Write-Log "Switching back to $currentBranch branch..." "Yellow"
        git checkout $currentBranch 2>&1 | Out-Null
        
        # Don't restore stashed changes - they may contain merge conflicts
        # Clear any stashes to prevent conflicts from being restored
        $stashList = git stash list 2>&1
        if ($stashList -match "Auto-stash before gh-pages deployment") {
            Write-Log "Clearing stashed changes to prevent merge conflicts..." "Yellow"
            git stash drop 2>&1 | Out-Null
        }
    }
    
} catch {
    Write-Log "ERROR: Failed to deploy" "Red"
    Write-Log $_.Exception.Message "Red"
    Write-Log "" "White"
    Write-Log "Troubleshooting:" "Yellow"
    Write-Log "  1. Check GITHUB_REPO is correct" "White"
    Write-Log "  2. Ensure you have push access" "White"
    Write-Log "  3. For private repos, set GITHUB_TOKEN" "White"
    Write-Log "  4. Check git status: git status" "White"
    Write-Log "  5. Check current branch: git branch" "White"
    Write-Log "  6. Check remote URL: git remote -v" "White"
    
    # Try to switch back to original branch
    if ($currentBranch) {
        Write-Log "Switching back to $currentBranch branch..." "Yellow"
        git checkout $currentBranch 2>&1 | Out-Null
        
        # Clear any stashes to prevent merge conflicts from being restored
        $stashList = git stash list 2>&1
        if ($stashList -match "Auto-stash before gh-pages deployment") {
            Write-Log "Clearing stashed changes to prevent merge conflicts..." "Yellow"
            git stash drop 2>&1 | Out-Null
        }
    }
    exit 1
}
```

---

## run_daily_analysis.ps1

```powershell
# Daily PRA Analysis Workflow
# Runs: pra_nighttime.py -> integrate_earthquakes.py -> upload_results.py
# Designed to run via Windows Task Scheduler at 12:00 PM GMT+8
#
# NOTE: This script processes ALL stations from stations.json automatically.
# To process specific stations only, set INTERMAGNET_STATIONS environment variable
# before running (e.g., $env:INTERMAGNET_STATIONS="KAK,HER")

$ErrorActionPreference = "Stop"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Ensure we process ALL stations (unset INTERMAGNET_STATIONS if it exists)
# This ensures the script processes all stations from stations.json
if (Test-Path Env:INTERMAGNET_STATIONS) {
    Remove-Item Env:INTERMAGNET_STATIONS
    Write-Host "Note: INTERMAGNET_STATIONS was unset - processing ALL stations" -ForegroundColor Yellow
}

# Log file
$LogDir = "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}
$LogFile = Join-Path $LogDir "daily_analysis_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

function Write-Log {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp] $Message"
    Write-Host $LogMessage
    Add-Content -Path $LogFile -Value $LogMessage
}

Write-Log "=========================================="
Write-Log "Starting Daily PRA Analysis Workflow"
Write-Log "=========================================="

try {
    # Step 1: Run main analysis
    Write-Log "Step 1: Running PRA analysis (pra_nighttime.py)..."
    python pra_nighttime.py 2>&1 | Tee-Object -FilePath $LogFile -Append
    if ($LASTEXITCODE -ne 0) {
        throw "PRA analysis failed with exit code $LASTEXITCODE"
    }
    Write-Log "PRA analysis completed successfully"
    
    # Step 2: Integrate earthquakes
    Write-Log "Step 2: Integrating earthquake data (integrate_earthquakes.py)..."
    python integrate_earthquakes.py 2>&1 | Tee-Object -FilePath $LogFile -Append
    if ($LASTEXITCODE -ne 0) {
        Write-Log "WARNING: Earthquake integration failed, continuing..."
    } else {
        Write-Log "Earthquake integration completed"
    }
    
    # Step 3: Prepare web files
    Write-Log "Step 3: Preparing web files (upload_results.py)..."
    python upload_results.py 2>&1 | Tee-Object -FilePath $LogFile -Append
    if ($LASTEXITCODE -ne 0) {
        throw "Web file preparation failed with exit code $LASTEXITCODE"
    }
    Write-Log "Web files prepared successfully"
    
    # Step 4: Deploy to GitHub Pages (optional)
    if ($env:GITHUB_REPO) {
        Write-Log "Step 4: Deploying to GitHub Pages..."
        powershell.exe -ExecutionPolicy Bypass -File "deploy_to_github.ps1" 2>&1 | Tee-Object -FilePath $LogFile -Append
        if ($LASTEXITCODE -ne 0) {
            Write-Log "WARNING: GitHub deployment failed, but analysis completed"
        } else {
            Write-Log "GitHub Pages deployment completed"
        }
    } else {
        Write-Log "Step 4: Skipping GitHub deployment (GITHUB_REPO not set)"
    }
    
    Write-Log "=========================================="
    Write-Log "Daily workflow completed successfully!"
    Write-Log "=========================================="
    
    exit 0
    
} catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    Write-Log "Stack trace: $($_.ScriptStackTrace)"
    exit 1
}

```

---

## requirements.txt

```text
numpy>=1.24.0,<2.0.0
pandas>=2.0.0
matplotlib>=3.7.0
requests>=2.31.0
scipy>=1.10.0
flask>=2.3.0
geopy>=2.3.0

```
