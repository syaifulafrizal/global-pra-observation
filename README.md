# PRA Nighttime Detection System

A real-time geomagnetic anomaly detection system using Polarization Ratio Analysis (PRA) for INTERMAGNET stations. This system employs Multitaper Spectral Analysis combined with Extreme Value Theory to detect anomalies that may correlate with earthquake occurrences.

## Features

- **Automated Processing**: Processes all INTERMAGNET stations automatically
- **Anomaly Detection**: Uses Multitaper (NW=3.5) + EVT + nZ z-score method
- **Earthquake Correlation**: Correlates detected anomalies with USGS earthquake data
- **Interactive Dashboard**: Global map visualization with color-coded station markers
- **Real-time Updates**: Daily automated processing and website updates

## Methodology

### Frequency Band
- **Range**: 0.095-0.110 Hz
- **Time Window**: 20:00-04:00 Local Time (nighttime)

### Detection Method
1. **Multitaper Spectral Analysis** (NW=3.5)
2. **Extreme Value Theory (EVT)** for threshold determination
3. **nZ Normalization** for z-score calculation
4. **SYM-H Index** for quiet period filtering

### Earthquake Correlation
- **Distance**: Within 200 km of station
- **Time Window**: 14 days before anomaly detection
- **Data Source**: USGS Earthquake Catalog

## Installation

### Requirements

```bash
pip install -r requirements.txt
```

### Dependencies

- Python 3.8+
- numpy (<2.0.0)
- pandas
- scipy
- matplotlib
- requests
- flask
- geopy

## Usage

### Manual Processing

Process all stations:
```bash
python pra_nighttime.py
```

Process specific stations:
```bash
$env:INTERMAGNET_STATIONS="KAK,HER,NGK"
python pra_nighttime.py
```

### Integrate Earthquake Data

```bash
python integrate_earthquakes.py
```

### Prepare Web Output

```bash
python upload_results.py
```

### Local Testing

```bash
python app.py
```

Then open: http://localhost:5000

### Deploy to GitHub Pages

```bash
$env:GITHUB_REPO="username/repo-name"
$env:GITHUB_BRANCH="gh-pages"
.\deploy_to_github.ps1
```

## Automation

### Windows Task Scheduler

1. Run `setup_windows_scheduler.ps1` as Administrator
2. Or manually create a task to run `run_daily_analysis.ps1` daily at 12:00 PM GMT+8

### Linux/Mac Cron

Add to crontab:
```bash
0 12 * * * /path/to/run_daily_analysis.sh
```

## Project Structure

```
pra-observation/
├── pra_nighttime.py          # Main analysis script
├── integrate_earthquakes.py  # Earthquake correlation
├── upload_results.py          # Web output preparation
├── download_symh.py          # SYM-H data download
├── app.py                    # Flask web server
├── static/                   # Frontend assets
│   ├── app.js
│   └── style.css
├── templates/                # HTML templates
├── web_output/               # Prepared web files
└── INTERMAGNET_DOWNLOADS/    # Station data
```

## Data Sources

- **INTERMAGNET**: Geomagnetic observatory data
- **OMNIWeb (NASA)**: SYM-H geomagnetic index
- **USGS**: Earthquake catalog

## Output Files

- `PRA_Night_{STATION}_{DATE}.json`: Analysis results
- `PRA_Night_{STATION}_{DATE}.csv`: Time series data
- `PRA_{STATION}_{DATE}.png`: Visualization plots
- `anomaly_master_table.csv`: Anomaly log
- `earthquake_correlations.csv`: EQ correlation data

## Web Dashboard

The interactive dashboard provides:
- Global map with all station locations
- Color-coded markers (gray: normal, orange: EQ correlation, red: false alarm)
- Summary statistics
- Station-specific analysis plots
- Earthquake correlation details

## License

This project is for research purposes.

## Acknowledgements

This research utilizes data and services from the following organizations:

- **INTERMAGNET** (International Real-time Magnetic Observatory Network) - Provides geomagnetic observatory data from stations worldwide. [https://www.intermagnet.org](https://www.intermagnet.org)

- **USGS** (United States Geological Survey) - Provides earthquake catalog data for correlation analysis. [https://earthquake.usgs.gov](https://earthquake.usgs.gov)

- **Universiti Putra Malaysia** - Research institution where this work was conducted. [https://www.upm.edu.my](https://www.upm.edu.my)

- **NASA OMNIWeb** - Provides SYM-H geomagnetic index data for quiet period determination.

## Author

**Nur Syaiful Afrizal**

- GitHub: [@syaifulafrizal](https://github.com/syaifulafrizal)

## Citation

If you use this code in your research, please acknowledge:
- INTERMAGNET for geomagnetic data
- USGS for earthquake data
- Universiti Putra Malaysia

## References

- Multitaper Spectral Analysis
- Extreme Value Theory for threshold estimation
- Polarization Ratio Analysis methodology
