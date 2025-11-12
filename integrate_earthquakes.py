#!/usr/bin/env python3
"""
Integrate earthquake data with PRA anomaly results
Run this after pra_nighttime.py to add earthquake correlations
"""

import os
from pathlib import Path
from load_stations import load_stations
from earthquake_integration import correlate_anomalies_with_earthquakes, save_earthquake_correlations

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
        
        # Correlate anomalies with earthquakes
        correlations = correlate_anomalies_with_earthquakes(station_code, results_folder)
        
        if not correlations.empty:
            # Save correlations
            save_earthquake_correlations(station_code, results_folder, correlations)
            
            results_summary[station_code] = {
                'anomalies_with_eq': len(correlations),
                'total_correlations': len(correlations)
            }
            print(f'  [OK] Found {len(correlations)} anomaly-earthquake correlations')
        else:
            results_summary[station_code] = {
                'anomalies_with_eq': 0,
                'total_correlations': 0
            }
            print(f'  [INFO] No earthquake correlations found')
    
    # Print summary
    print(f'\n{"="*60}')
    print('Summary:')
    print(f'{"="*60}')
    
    total_correlations = sum(r['total_correlations'] for r in results_summary.values())
    stations_with_correlations = sum(1 for r in results_summary.values() if r['total_correlations'] > 0)
    
    print(f'Total stations processed: {len(results_summary)}')
    print(f'Stations with correlations: {stations_with_correlations}')
    print(f'Total correlations found: {total_correlations}')
    
    # Show stations with correlations
    if stations_with_correlations > 0:
        print(f'\nStations with earthquake correlations:')
        for station, data in results_summary.items():
            if data['total_correlations'] > 0:
                print(f'  {station}: {data["total_correlations"]} correlations')

if __name__ == '__main__':
    main()

