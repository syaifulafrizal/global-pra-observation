# PRA Nighttime Detection System

Polarization Ratio Analysis (PRA) for geomagnetic anomaly detection using INTERMAGNET station data.

## Features

- **Automatic Processing**: Processes 64+ INTERMAGNET stations automatically
- **Advanced Detection**: Multitaper spectral analysis (NW=3.5) + EVT + nZ z-score
- **Earthquake Correlation**: Correlates anomalies with USGS earthquake data (200km, 14 days)
- **Interactive Dashboard**: Web-based visualization with world map
- **Local Server**: Runs entirely on local machine, no external hosting needed

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run Analysis

```bash
# Process all stations automatically
python pra_nighttime.py
```

### 3. Integrate Earthquakes (Optional)

```bash
python integrate_earthquakes.py
```

### 4. Prepare Web Files

```bash
python upload_results.py
```

### 5. Start Web Server

```bash
python app.py
```

Open browser: **http://localhost:5000**

## Project Structure

```
pra-observation/
├── pra_nighttime.py          # Main analysis script
├── integrate_earthquakes.py  # Earthquake correlation
├── upload_results.py         # Web file preparation
├── app.py                    # Flask web server
├── download_symh.py          # SYM-H index download
├── earthquake_integration.py # EQ correlation functions
├── load_stations.py          # Station data loader
├── stations.json             # Station metadata
├── requirements.txt          # Python dependencies
├── static/                   # Frontend assets
│   ├── app.js
│   └── style.css
└── INTERMAGNET_DOWNLOADS/    # Processed data (generated)
```

## Configuration

Set environment variable to process specific stations:

```bash
# Windows PowerShell
$env:INTERMAGNET_STATIONS="KAK,HER,NGK"
python pra_nighttime.py

# Linux/Mac
export INTERMAGNET_STATIONS="KAK,HER,NGK"
python pra_nighttime.py
```

Leave empty to process all stations from `stations.json`.

## Method

- **Spectral Analysis**: Multitaper method (NW=3.5)
- **Threshold**: Extreme Value Theory (Generalized Pareto Distribution)
- **Filtering**: nZ z-score guard (station-specific)
- **Time Window**: 20:00-04:00 Local Time
- **Frequency Band**: 0.095-0.110 Hz

## Web Deployment

The system is designed for local server deployment. The Flask app serves files from:
- `web_output/` (prepared static files)
- `INTERMAGNET_DOWNLOADS/` (source data)

For production, use a WSGI server like `gunicorn` or `waitress`:

```bash
# Using waitress (Windows/Linux)
pip install waitress
waitress-serve --host=0.0.0.0 --port=5000 app:app

# Using gunicorn (Linux)
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## License

See LICENSE file for details.

## Author

Nur Syaiful Afrizal
