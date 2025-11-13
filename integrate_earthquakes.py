#!/usr/bin/env python3
"""
Integrate earthquake data with PRA anomaly results
Run this after pra_nighttime.py to add earthquake correlations
"""

import os
from pathlib import Path
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
    
    # Get recent earthquakes for map display (today only)
    print(f'\n{"="*60}')
    print('Fetching today\'s earthquakes for map display...')
    recent_eq = get_recent_earthquakes_all_stations(days=1, min_magnitude=5.5)
    if not recent_eq.empty:
        # Save to web_output for frontend
        web_data_dir = Path('web_output') / 'data'
        web_data_dir.mkdir(parents=True, exist_ok=True)
        recent_eq_file = web_data_dir / 'recent_earthquakes.csv'
        recent_eq.to_csv(recent_eq_file, index=False)
        print(f'  [OK] Saved {len(recent_eq)} today\'s earthquakes (M>=5.5) to {recent_eq_file}')
    else:
        print(f'  [INFO] No earthquakes (M>=5.5) found for today')
    
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

