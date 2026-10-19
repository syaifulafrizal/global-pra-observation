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
from zoneinfo import ZoneInfo
from result_validation import result_is_usable
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
        'starttime': utc_naive(start_date).strftime('%Y-%m-%dT%H:%M:%S'),
        'endtime': utc_naive(end_date).strftime('%Y-%m-%dT%H:%M:%S'),
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
        
        if 'features' not in data:
            raise ValueError('USGS response has no features field')
        if not data['features']:
            return empty_earthquakes(True)
        
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
        df.attrs['query_succeeded'] = True
        print(f'Found {len(df)} earthquakes')
        return df
        
    except Exception as e:
        print(f'Error fetching earthquakes: {e}')
        return empty_earthquakes(False)

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in km"""
    return geodesic((lat1, lon1), (lat2, lon2)).kilometers

def utc_naive(value):
    """USGS times are UTC; keep comparisons consistent with existing CSVs."""
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError('Missing event time')
    return stamp.tz_convert('UTC').tz_localize(None) if stamp.tzinfo else stamp


def empty_earthquakes(succeeded):
    frame = pd.DataFrame(columns=['time', 'latitude', 'longitude', 'magnitude',
                                  'place', 'id', 'distance_km', 'days_from_anomaly'])
    frame.attrs['query_succeeded'] = succeeded
    return frame


def station_timezone(station_code):
    from load_stations import get_station_info
    info = get_station_info(station_code) or {}
    return ZoneInfo(info.get('timezone', 'UTC'))


def anomaly_detection_time(anomaly, station_code):
    """Use actual detection time, or the end of a legacy local nighttime range."""
    explicit = anomaly.get('DetectionTimeUTC')
    if explicit is not None and not pd.isna(explicit):
        return utc_naive(explicit)
    end = str(anomaly['Range']).split(' - ')[1]
    local = pd.to_datetime(end, format='%d/%m/%Y %H:%M').tz_localize(station_timezone(station_code))
    return utc_naive(local)


def anomaly_result_date(anomaly):
    end = str(anomaly['Range']).split(' - ')[1].split()[0]
    return pd.to_datetime(end, format='%d/%m/%Y')


def find_nearby_earthquakes(station_code, anomaly_date, days_before=0, days_after=14,
                           max_distance_km=200, min_magnitude=4.0):
    """Find events relative to the detection time, without querying the future."""
    lat, lon = get_station_coordinates(station_code)
    if lat is None or lon is None:
        return empty_earthquakes(False)
    detection = utc_naive(anomaly_date)
    start = detection - timedelta(days=days_before)
    end = min(detection + timedelta(days=days_after), pd.Timestamp.utcnow().tz_localize(None))
    if start >= end:
        return empty_earthquakes(True)
    events = fetch_usgs_earthquakes(start, end, min_magnitude=min_magnitude,
                                  latitude=lat, longitude=lon, max_radius_km=max_distance_km)
    if events.empty:
        return events
    events = events.copy()
    events['time'] = pd.to_datetime(events['time'], utc=True).dt.tz_localize(None)
    events['distance_km'] = [calculate_distance(lat, lon, row['latitude'], row['longitude'])
                             for _, row in events.iterrows()]
    events['days_from_anomaly'] = (events['time'] - detection).dt.total_seconds() / 86400
    return events[(events['time'] >= start) & (events['time'] <= end)
                  & (events['distance_km'] <= max_distance_km)].sort_values('time')


def correlate_anomalies_with_earthquakes(station_code, results_folder):
    """A match is M>=5 within 200 km during the 14 days AFTER detection."""
    path = results_folder / 'anomaly_master_table.csv'
    if not path.exists():
        return pd.DataFrame()
    try:
        anomalies = pd.read_csv(path)
    except (ValueError, OSError):
        return pd.DataFrame()
    correlations = []
    now = pd.Timestamp.utcnow().tz_localize(None)
    for _, anomaly in anomalies.drop_duplicates('Range', keep='last').iterrows():
        try:
            detection = anomaly_detection_time(anomaly, station_code)
            result_date = anomaly_result_date(anomaly)
        except (ValueError, KeyError, IndexError, TypeError):
            continue
        events = find_nearby_earthquakes(station_code, detection, days_before=0,
                                         days_after=14, max_distance_km=200, min_magnitude=5.0)
        reliable = events[events['magnitude'] >= 5.0] if not events.empty else events
        complete = now >= detection + timedelta(days=14)
        status = ('FP' if complete else 'Pending') if events.attrs.get('query_succeeded', True) else 'Unknown'
        row = {
            'anomaly_date': result_date, 'anomaly_range': anomaly['Range'],
            'anomaly_times': anomaly.get('Times', ''), 'detection_time_utc': detection,
            'earthquake_time': None, 'earthquake_magnitude': None,
            'earthquake_distance_km': None, 'earthquake_place': None,
            'days_before_anomaly': None, 'days_after_anomaly': None,
            'total_earthquakes': len(events), 'reliable_earthquakes': len(reliable),
            'status': status,
        }
        if not reliable.empty:
            closest = reliable.loc[reliable['distance_km'].idxmin()]
            row.update(earthquake_time=closest['time'], earthquake_magnitude=closest['magnitude'],
                       earthquake_distance_km=closest['distance_km'], earthquake_place=closest['place'],
                       days_after_anomaly=closest['days_from_anomaly'],
                       days_before_anomaly=-closest['days_from_anomaly'], status='TP')
        correlations.append(row)
    return pd.DataFrame(correlations)


def find_false_negatives(station_code, results_folder, days_lookback=14):
    """Count a missed event only when the preceding 14 completed nights were observed."""
    lat, lon = get_station_coordinates(station_code)
    if lat is None or lon is None:
        return pd.DataFrame()
    coverage = {}
    ledger = results_folder / 'analysis_coverage.csv'
    if ledger.exists():
        for row in pd.read_csv(ledger).to_dict('records'):
            coverage[str(row['date'])] = str(row.get('complete')).lower() == 'true'
    for path in results_folder.glob('PRA_Night_*.json'):
        try:
            result = json.loads(path.read_text())
            quality = result.get('data_quality', {})
            coverage[result['date']] = (result_is_usable(result) and quality.get('status') == 'complete'
                                        and quality.get('symh_verified', False))
        except (ValueError, KeyError, OSError):
            continue
    if not coverage:
        return pd.DataFrame()
    end = pd.Timestamp.utcnow().tz_localize(None)
    events = fetch_usgs_earthquakes(end - timedelta(days=days_lookback), end,
                                  min_magnitude=5.0, latitude=lat, longitude=lon, max_radius_km=200)
    if events.empty:
        frame = pd.DataFrame(columns=['earthquake_time', 'earthquake_magnitude',
            'earthquake_distance_km', 'earthquake_place', 'earthquake_latitude',
            'earthquake_longitude', 'earthquake_id', 'coverage_verified'])
        frame.attrs['query_succeeded'] = events.attrs.get('query_succeeded', True)
        return frame
    detections = []
    anomaly_file = results_folder / 'anomaly_master_table.csv'
    if anomaly_file.exists():
        for row in pd.read_csv(anomaly_file).to_dict('records'):
            try:
                detections.append(anomaly_detection_time(row, station_code))
            except (ValueError, KeyError, IndexError, TypeError):
                continue
    missed = []
    for _, event in events.iterrows():
        when = utc_naive(event['time'])
        local = when.tz_localize('UTC').tz_convert(station_timezone(station_code))
        last_night = local.date() if local.hour >= 4 else local.date() - timedelta(days=1)
        observed = all(coverage.get((last_night - timedelta(days=i)).isoformat(), False)
                       for i in range(14))
        predicted = any(timedelta(0) <= when - detection <= timedelta(days=14)
                        for detection in detections)
        distance = calculate_distance(lat, lon, event['latitude'], event['longitude'])
        if observed and not predicted and distance <= 200:
            missed.append({
                'earthquake_time': event['time'], 'earthquake_magnitude': event['magnitude'],
                'earthquake_distance_km': distance, 'earthquake_place': event['place'],
                'earthquake_latitude': event['latitude'], 'earthquake_longitude': event['longitude'],
                'earthquake_id': event.get('id'), 'coverage_verified': True,
            })
    frame = pd.DataFrame(missed, columns=['earthquake_time', 'earthquake_magnitude',
        'earthquake_distance_km', 'earthquake_place', 'earthquake_latitude',
        'earthquake_longitude', 'earthquake_id', 'coverage_verified'])
    frame.attrs['query_succeeded'] = events.attrs.get('query_succeeded', True)
    return frame


def save_earthquake_correlations(station_code, results_folder, correlations_df):
    """Save earthquake correlation results"""
    if correlations_df.empty:
        return
    
    output_file = results_folder / 'earthquake_correlations.csv'
    correlations_df.to_csv(output_file, index=False)
    print(f'Saved earthquake correlations: {output_file}')

def save_false_negatives(station_code, results_folder, false_negatives_df):
    """Save false negative earthquakes"""
    if false_negatives_df.empty and not false_negatives_df.attrs.get('query_succeeded', False):
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

