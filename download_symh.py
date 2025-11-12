#!/usr/bin/env python3
"""
Download SYM-H geomagnetic index from NASA CDAWeb
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# NASA CDAWeb API
CDAWEB_BASE = 'https://cdaweb.gsfc.nasa.gov/sp_phys/data/omni/omni2_h0_mrg1hr/'

def download_symh_cdaweb(start_date, end_date, cache_folder):
    """Download SYM-H from NASA CDAWeb"""
    cache_file = cache_folder / f'SYMH_{start_date.strftime("%Y%m%d")}_{end_date.strftime("%Y%m%d")}.csv'
    
    # Check cache
    if cache_file.exists():
        try:
            df = pd.read_csv(cache_file, parse_dates=['Time'], index_col='Time')
            if not df.empty:
                print(f'Using cached SYM-H data: {cache_file.name}')
                return df
        except:
            pass
    
    print(f'Downloading SYM-H from NASA CDAWeb: {start_date.date()} to {end_date.date()}')
    
    try:
        # CDAWeb uses year-based files
        years = range(start_date.year, end_date.year + 1)
        all_data = []
        
        for year in years:
            # OMNI2 hourly data file naming: YYYY format
            # Try different possible URLs
            urls = [
                f'https://cdaweb.gsfc.nasa.gov/sp_phys/data/omni/omni2_h0_mrg1hr/{year}/omni2_h0_mrg1hr_{year}_v01.cdf',
                f'https://spdf.gsfc.nasa.gov/pub/data/omni/omni2_h0_mrg1hr/{year}/omni2_h0_mrg1hr_{year}_v01.cdf',
            ]
            
            # Alternative: Use OMNIWeb web interface
            # For now, use a simpler approach with OMNIWeb's web service
            
        # Use OMNIWeb web service instead (more reliable)
        return download_symh_omniweb(start_date, end_date, cache_file)
        
    except Exception as e:
        print(f'CDAWeb download failed: {e}')
        return download_symh_omniweb(start_date, end_date, cache_file)

def download_symh_omniweb(start_date, end_date, cache_file):
    """Download SYM-H using OMNIWeb web service"""
    try:
        # OMNIWeb web interface URL
        base_url = 'https://omniweb.gsfc.nasa.gov/cgi/nx1.cgi'
        
        # OMNIWeb data is only available up to 2025-10-30 (as of Nov 2025)
        # Limit dates to available range
        omni_max_date = datetime(2025, 10, 30)
        omni_min_date = datetime(1963, 11, 28)
        
        # Adjust dates if they're outside the available range
        if end_date > omni_max_date:
            end_date = omni_max_date
            print(f'[INFO] OMNIWeb data only available up to {omni_max_date.date()}, adjusting end date')
        
        if start_date < omni_min_date:
            start_date = omni_min_date
            print(f'[INFO] OMNIWeb data starts from {omni_min_date.date()}, adjusting start date')
        
        # If start_date > end_date after adjustment, return empty
        if start_date > end_date:
            print(f'[WARNING] Date range adjusted to empty - OMNIWeb data not available for requested dates')
            return pd.DataFrame(columns=['SYMH', 'Disturbed'])
        
        # Format dates (OMNIWeb needs dates in YYYYMMDD format)
        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        
        # Parameters for OMNIWeb
        # SYM-H is variable 50 in OMNI2
        params = {
            'activity': 'retrieve',
            'res': 'hour',
            'spacecraft': 'omni2',
            'start_date': start_str,
            'end_date': end_str,
            'vars': '50',  # SYM-H index (variable 50)
            'format': 'ascii'
        }
        
        print(f'Requesting SYM-H from OMNIWeb ({start_str} to {end_str})...')
        response = requests.get(base_url, params=params, timeout=120)
        response.raise_for_status()
        
        # Check if response is valid
        if len(response.text) < 100:
            raise ValueError('OMNIWeb response too short - may be an error page')
        
        # Parse the response - OMNIWeb returns different formats
        lines = response.text.split('\n')
        
        # Debug: Save response for inspection (optional)
        # with open('omniweb_response.txt', 'w') as f:
        #     f.write(response.text)
        
        # Find data start - look for header line with "YEAR" or data lines
        data_start = 0
        header_found = False
        
        # First, look for header line
        for i, line in enumerate(lines):
            line_upper = line.upper().strip()
            # Look for header indicators
            if ('YEAR' in line_upper and 'DOY' in line_upper) or \
               ('YEAR' in line_upper and 'HOUR' in line_upper) or \
               (line_upper.startswith('YEAR') and len(line.split()) >= 3):
                data_start = i + 1  # Data starts after header
                header_found = True
                print(f'Found header at line {i}, data starts at {data_start}')
                break
        
        # If no header found, look for first numeric data line
        if not header_found:
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                # Check if line starts with 4-digit year
                parts = line_stripped.split()
                if len(parts) >= 3:
                    try:
                        # Try to parse first part as year
                        year_test = int(parts[0])
                        if 1950 <= year_test <= 2100:  # Reasonable year range
                            data_start = i
                            print(f'Found data start at line {i} (no header)')
                            break
                    except (ValueError, IndexError):
                        continue
        
        # Last resort: skip known header lines and find first data-like line
        if data_start == 0:
            # OMNIWeb typically has ~50-60 header lines
            for i, line in enumerate(lines[50:], start=50):
                line_stripped = line.strip()
                if line_stripped and len(line_stripped) > 10:
                    parts = line_stripped.split()
                    if len(parts) >= 3:
                        try:
                            year_test = int(parts[0])
                            if 1950 <= year_test <= 2100:
                                data_start = i
                                print(f'Found data start at line {i} (after skipping headers)')
                                break
                        except (ValueError, IndexError):
                            continue
        
        if data_start == 0:
            # Try to get a sample of the response for debugging
            sample = '\n'.join(lines[:30])
            raise ValueError(f'Could not find data start in OMNI response. First 30 lines:\n{sample}')
        
        # Parse data lines
        data_lines = []
        for line in lines[data_start:]:
            line_stripped = line.strip()
            # Skip empty lines, comments, and non-data lines
            if not line_stripped or line_stripped.startswith('#') or \
               line_stripped.startswith('BEGIN') or line_stripped.startswith('END') or \
               'YEAR' in line_stripped.upper():
                continue
            # Check if line has numeric data
            parts = line_stripped.split()
            if len(parts) >= 3:
                try:
                    # Try to parse first part as number
                    float(parts[0])
                    data_lines.append(line_stripped)
                except (ValueError, IndexError):
                    continue
        
        if not data_lines:
            raise ValueError('No data lines found after parsing')
        
        # Parse columns - OMNI format varies, try different column positions
        records = []
        for line in data_lines[:2000]:  # Limit to avoid memory issues
            parts = line.split()
            if len(parts) < 3:
                continue
            
            try:
                # Try different column positions for SYM-H (usually column 40-50)
                # But for simplicity, let's try to find year, doy, hour first
                year = int(parts[0])
                doy = int(parts[1])
                hour = int(parts[2])
                
                # SYM-H is at column 40 in OMNI2 hourly format (0-indexed)
                # But let's be flexible and check multiple positions
                symh = np.nan
                
                # Try known positions first (OMNI2 hourly format)
                symh_positions = [40, 41, 39, 38]  # Common positions for SYM-H
                for pos in symh_positions:
                    if pos < len(parts):
                        try:
                            val = float(parts[pos])
                            # SYM-H typically ranges from -500 to +500, and is not 9999
                            if -500 <= val <= 500 and val not in [9999, 999.99, 99.99]:
                                symh = val
                                break
                        except (ValueError, IndexError):
                            continue
                
                # If not found at known positions, search all columns
                if np.isnan(symh):
                    for i, part in enumerate(parts[3:min(60, len(parts))]):
                        try:
                            val = float(part)
                            # SYM-H typically ranges from -500 to +500
                            if -500 <= val <= 500 and val not in [9999, 999.99, 99.99]:
                                symh = val
                                break
                        except (ValueError, IndexError):
                            continue
                
                # If still no SYM-H found, skip this record
                if np.isnan(symh):
                    continue
                
                # Convert to datetime
                dt = datetime(year, 1, 1) + timedelta(days=doy-1, hours=hour)
                records.append({'Time': dt, 'SYMH': symh})
                
            except (ValueError, IndexError, OverflowError):
                continue
        
        if not records:
            raise ValueError('No valid records parsed')
        
        # Create DataFrame
        df = pd.DataFrame(records)
        df['Time'] = pd.to_datetime(df['Time'])
        df = df.set_index('Time')
        df = df.sort_index()
        
        # Add disturbed flag
        df['Disturbed'] = df['SYMH'] < -30
        
        # Remove NaN rows
        df = df.dropna(subset=['SYMH'])
        
        # Cache the result
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache_file)
        print(f'Saved SYM-H data to cache: {cache_file.name}')
        print(f'Retrieved {len(df)} records')
        
        return df
        
    except Exception as e:
        print(f'OMNIWeb download failed: {e}')
        print('Returning empty DataFrame - will use fallback (assume quiet)')
        return pd.DataFrame(columns=['SYMH', 'Disturbed'])

if __name__ == '__main__':
    # Test download
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo('Asia/Tokyo')
    
    end_date = datetime.now(TZ)
    start_date = end_date - timedelta(days=3)
    
    cache_folder = Path('INTERMAGNET_DOWNLOADS') / '_cache'
    df = download_symh_omniweb(start_date, end_date, cache_folder / 'test_symh.csv')
    
    print(f'\nDownloaded {len(df)} records')
    print(f'Date range: {df.index.min()} to {df.index.max()}')
    print(f'SYM-H range: {df["SYMH"].min():.1f} to {df["SYMH"].max():.1f} nT')

