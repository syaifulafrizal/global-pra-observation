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

