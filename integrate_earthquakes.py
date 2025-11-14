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
        
        # Correlate anomalies with earthquakes (magnitude >= 5.5 for reliability)
        correlations = correlate_anomalies_with_earthquakes(station_code, results_folder)
        
        # Find false negatives (EQ >= 5.5 occurred but no anomaly detected)
        false_negatives = find_false_negatives(station_code, results_folder, days_lookback=14)
        
        if not correlations.empty:
            # Save correlations
            save_earthquake_correlations(station_code, results_folder, correlations)
            print(f'  [OK] Found {len(correlations)} anomaly-earthquake correlations (M>=5.5)')
        else:
            print(f'  [INFO] No earthquake correlations found (M>=5.5)')
        
        if not false_negatives.empty:
            # Save false negatives
            save_false_negatives(station_code, results_folder, false_negatives)
            print(f'  [INFO] Found {len(false_negatives)} false negatives (EQ M>=5.5 without anomaly)')
        
        results_summary[station_code] = {
            'anomalies_with_eq': len(correlations),
            'total_correlations': len(correlations),
            'false_negatives': len(false_negatives)
        }
    
    # Clean old earthquake stats files to ensure fresh calculation
    web_data_dir = Path('web_output') / 'data'
    web_data_dir.mkdir(parents=True, exist_ok=True)
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
    print('Fetching global earthquakes (M>=5.5) for last 7 days...')
    from earthquake_integration import get_global_earthquakes_today, calculate_distance, fetch_usgs_earthquakes
    
    today = datetime.now().date()
    web_data_dir = Path('web_output') / 'data'
    web_data_dir.mkdir(parents=True, exist_ok=True)
    
    # Process each of the last 7 days
    for days_back in range(7):
        target_date = today - timedelta(days=days_back)
        date_str = target_date.strftime('%Y-%m-%d')
        
        # Fetch earthquakes for this date
        start_date = datetime.combine(target_date, datetime.min.time())
        end_date = start_date + timedelta(days=1)
        
        print(f'  Fetching earthquakes for {date_str}...')
        day_eq = fetch_usgs_earthquakes(start_date, end_date, min_magnitude=5.5)
        
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
            'min_magnitude': 5.5
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
    print(f'  [INFO] Earthquakes (M>=5.5) globally today: {global_count}')
    print(f'  [INFO] Earthquakes (M>=5.5) within 200km of stations: {within_200km_count}')
    
    # Print summary
    print(f'\n{"="*60}')
    print('Summary:')
    print(f'{"="*60}')
    
    total_correlations = sum(r['total_correlations'] for r in results_summary.values())
    total_false_negatives = sum(r['false_negatives'] for r in results_summary.values())
    stations_with_correlations = sum(1 for r in results_summary.values() if r['total_correlations'] > 0)
    
    print(f'Total stations processed: {len(results_summary)}')
    print(f'Stations with correlations (M>=5.5): {stations_with_correlations}')
    print(f'Total reliable correlations (M>=5.5): {total_correlations}')
    print(f'Total false negatives (M>=5.5): {total_false_negatives}')
    
    # Show stations with correlations
    if stations_with_correlations > 0:
        print(f'\nStations with earthquake correlations (M>=5.5):')
        for station, data in results_summary.items():
            if data['total_correlations'] > 0:
                print(f'  {station}: {data["total_correlations"]} correlations')

if __name__ == '__main__':
    main()

