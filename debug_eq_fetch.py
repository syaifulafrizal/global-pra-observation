from datetime import datetime, timedelta
from pathlib import Path
from earthquake_integration import fetch_usgs_earthquakes

def test_fetch():
    today = datetime.now().date()
    target_date = today
    date_str = target_date.strftime('%Y-%m-%d')
    
    start_date = datetime.combine(target_date, datetime.min.time())
    end_date = start_date + timedelta(days=1)
    
    print(f"Fetching for {date_str}")
    print(f"Range: {start_date} to {end_date}")
    
    df = fetch_usgs_earthquakes(start_date, end_date, min_magnitude=5.0)
    print(f"Found {len(df)} earthquakes")
    
    filename = f"recent_earthquakes_{date_str}.csv"
    print(f"Saving to {filename} in {Path('.').absolute()}")
    
    if not df.empty:
        df.to_csv(filename, index=False)
    else:
        print("Empty dataframe, creating empty file")
        with open(filename, 'w') as f:
            f.write("header\n")
            
    if Path(filename).exists():
        print(f"SUCCESS: {filename} created")
    else:
        print(f"FAILURE: {filename} not found")

if __name__ == "__main__":
    test_fetch()
