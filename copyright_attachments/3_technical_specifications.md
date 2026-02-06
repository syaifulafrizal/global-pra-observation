# GEMPRA Technical Specifications

## System Requirements

### Backend Processing Environment

- **Operating System**: Windows 10/11, Linux (Ubuntu 20.04+)
- **Python Version**: 3.8 or higher
- **Memory**: Minimum 4GB RAM (8GB recommended)
- **Storage**: 10GB free space for data processing
- **Network**: Stable internet connection for API access

### Frontend Requirements

- **Browser Compatibility**:
  - Chrome 90+
  - Firefox 88+
  - Safari 14+
  - Edge 90+
- **JavaScript**: ES6+ support required
- **Screen Resolution**: Minimum 1280x720 (responsive design)

---

## Technology Stack

### Backend Technologies

#### Core Language

- **Python 3.x**
  - Version: 3.8+
  - Purpose: Data processing, analysis, and automation

#### Scientific Computing Libraries

```python
numpy >= 1.21.0          # Numerical computations
scipy >= 1.7.0           # Scientific algorithms
pandas >= 1.3.0          # Data manipulation
matplotlib >= 3.4.0      # Plotting and visualization
```

#### Geospatial Analysis

```python
geopy >= 2.2.0           # Distance calculations
```

#### Data Acquisition

```python
requests >= 2.26.0       # HTTP requests for API calls
```

#### File I/O

```python
json                     # JSON parsing (built-in)
csv                      # CSV handling (built-in)
pathlib                  # Path operations (built-in)
```

### Frontend Technologies

#### Core Web Technologies

- **HTML5**: Semantic markup, responsive structure
- **CSS3**: Modern styling, flexbox, grid layouts
- **JavaScript (ES6+)**: Interactive functionality

#### Visualization Libraries

```html
<!-- Leaflet.js for Interactive Maps -->
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />

<!-- Chart.js for Data Visualization -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
```

---

## API Integrations

### 1. USGS Earthquake API

**Endpoint**: `https://earthquake.usgs.gov/fdsnws/event/1/query`

**Parameters**:

```python
{
    'format': 'geojson',
    'starttime': 'YYYY-MM-DD',
    'endtime': 'YYYY-MM-DD',
    'minmagnitude': 5.0,
    'latitude': float,
    'longitude': float,
    'maxradiuskm': 200
}
```

**Response Format**: GeoJSON
**Rate Limit**: No strict limit (reasonable use policy)
**Documentation**: https://earthquake.usgs.gov/fdsnws/event/1/

### 2. INTERMAGNET Data Access

**Source**: Individual station FTP/HTTP servers
**Format**: IAGA-2002 format (text-based)
**Sampling**: 1-minute resolution
**Components**: H, D, Z magnetic field vectors
**Access**: Public data with attribution

---

## Data Formats

### Input Data

#### Geomagnetic Data (IAGA-2002)

```
DATE       TIME         DOY     H       D       Z       F
2024-01-01 00:00:00.000  001  21234.5  -123.4  41234.5  45678.9
```

#### Earthquake Data (GeoJSON)

```json
{
  "type": "Feature",
  "properties": {
    "mag": 5.5,
    "place": "10km E of Example City",
    "time": 1704067200000,
    "type": "earthquake"
  },
  "geometry": {
    "type": "Point",
    "coordinates": [longitude, latitude, depth]
  }
}
```

### Output Data

#### Station Analysis JSON

```json
{
  "station": "KAK",
  "date": "2024-01-01",
  "is_anomalous": true,
  "threshold": 2.5,
  "n_anomaly_hours": 3,
  "polarization_ratios": [1.2, 1.5, 2.8, ...],
  "times": ["20:00", "21:00", "22:00", ...]
}
```

#### Earthquake Correlation CSV

```csv
anomaly_date,earthquake_time,earthquake_magnitude,earthquake_distance_km,status
2024-01-01,2024-01-05 14:23:00,5.5,145.2,TP
```

#### Aggregated Data JSON

```json
{
  "date": "2024-01-01",
  "generated_at": "2024-01-01T12:00:00Z",
  "stations": {
    "KAK": { /* station data */ },
    "PAG": { /* station data */ }
  },
  "earthquake_correlations": {
    "KAK": [ /* correlations */ ]
  },
  "metadata": { /* station info */ }
}
```

---

## Processing Algorithms

### 1. Multitaper Spectral Analysis

**Implementation**: SciPy `scipy.signal.windows.dpss`

**Parameters**:

- Time-bandwidth product (NW): 3.5
- Number of tapers: 6
- FFT length: 512 points

**Code Reference**:

```python
from scipy.signal import windows
from scipy.fft import fft

# Generate DPSS tapers
tapers, eigenvalues = windows.dpss(N, NW, Kmax)

# Apply tapers and compute spectra
spectra = []
for taper in tapers:
    windowed = data * taper
    spectrum = fft(windowed)
    spectra.append(spectrum)

# Average across tapers
avg_spectrum = np.mean(spectra, axis=0)
```

### 2. Extreme Value Theory (EVT)

**Distribution**: Generalized Extreme Value (GEV)

**Implementation**: SciPy `scipy.stats.genextreme`

**Process**:

1. Collect 30-day baseline data
2. Fit GEV distribution
3. Calculate 95th percentile threshold
4. Flag values exceeding threshold as anomalies

### 3. Geospatial Distance Calculation

**Method**: Haversine formula via Geopy

**Code**:

```python
from geopy.distance import geodesic

distance_km = geodesic(
    (station_lat, station_lon),
    (earthquake_lat, earthquake_lon)
).kilometers
```

---

## Performance Specifications

### Processing Speed

- **Single Station Analysis**: ~2-5 seconds
- **51 Stations (Parallel)**: ~30-60 seconds
- **Earthquake Correlation**: ~5-10 seconds per station
- **Data Aggregation**: ~10-15 seconds

### Data Volume

- **Per Station Per Day**: ~50 KB (JSON)
- **Aggregated File Per Day**: ~2-3 MB (all stations)
- **7-Day Rolling Window**: ~15-20 MB total
- **Historical Archives**: ~500 MB (6 months)

### Network Optimization

- **Original Requests**: 350+ per page load
- **Optimized Requests**: 7 per page load
- **Reduction**: 98%
- **Load Time**: <2 seconds (typical)

---

## Deployment Specifications

### Windows Task Scheduler Configuration

```powershell
# Scheduled Task Configuration
# Task Name: GEMPRA Daily Processing
# Trigger: Daily at specific time (GMT+8 timezone)
# Action: Run PowerShell script

# Example PowerShell automation script
# File: run_daily_processing.ps1

# Set working directory
Set-Location "C:\Users\SYAIFUL\Downloads\pra-observation"

# Activate Python environment (if using virtual env)
# & ".\venv\Scripts\Activate.ps1"

# Run data processing
Write-Host "Starting GEMPRA data processing..."
python integrate_earthquakes.py
python upload_results.py

# Git operations for deployment
git add web_output/*
git commit -m "Automated update: $(Get-Date -Format 'yyyy-MM-dd HH:mm') GMT+8"
git push origin main

Write-Host "Processing complete!"
```

**Task Scheduler Settings**:

- **Trigger**: Daily at configured time (e.g., 6:00 AM GMT+8)
- **Action**: Run PowerShell script with execution policy bypass
- **Conditions**: Run only when computer is on AC power
- **Settings**: Allow task to run on demand, restart on failure

### File Structure

```
web_output/
├── index.html
├── static/
│   ├── app.js
│   └── style.css
├── data/
│   ├── stations.json
│   ├── aggregated_2024-01-01.json
│   ├── aggregated_2024-01-02.json
│   └── ...
└── figures/
    ├── KAK/
    │   └── PRA_Night_KAK_20240101.png
    └── ...
```

---

## Security & Privacy

### Data Protection

- **Public Data Only**: All data sources are publicly available
- **No User Data**: No personal information collected
- **No Authentication**: Open access platform
- **HTTPS**: Served over secure connection via GitHub Pages

### Code Security

- **Version Control**: Git-based tracking
- **Code Review**: Manual review before deployment
- **Dependency Management**: Regular updates for security patches

---

## Accessibility

### WCAG 2.1 Compliance

- **Color Contrast**: AA level compliance
- **Keyboard Navigation**: Full keyboard accessibility
- **Screen Readers**: Semantic HTML for compatibility
- **Responsive Design**: Mobile-friendly interface

### Internationalization

- **Language**: English (primary)
- **Date Formats**: ISO 8601 standard
- **Time Zones**: UTC with local time conversion
