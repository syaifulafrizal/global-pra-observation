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
    """Dilate disturbed minutes by ±guardMin"""
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
        time_blocks.append(f'{h_str}–{h_end}')
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
