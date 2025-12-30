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

