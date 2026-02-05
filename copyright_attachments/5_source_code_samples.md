# GEMPRA Source Code Samples

This document contains key source code excerpts demonstrating the core functionality of the GEMPRA platform.

---

## 1. Polarization Ratio Analysis (PRA) - Python

### Core PRA Calculation Function

```python
import numpy as np
from scipy import signal
from scipy.stats import genextreme

def calculate_polarization_ratio(h_component, d_component, z_component, 
                                  sampling_rate=60, nw=3.5):
    """
    Calculate Polarization Ratio using Multitaper Spectral Analysis.
    
    Parameters:
    -----------
    h_component : array-like
        Horizontal (H) magnetic field component
    d_component : array-like
        Declination (D) magnetic field component
    z_component : array-like
        Vertical (Z) magnetic field component
    sampling_rate : int
        Sampling rate in seconds (default: 60 for 1-minute data)
    nw : float
        Time-bandwidth product for multitaper (default: 3.5)
    
    Returns:
    --------
    pr : float
        Polarization Ratio value
    """
    # Multitaper spectral analysis parameters
    n_samples = len(h_component)
    k_tapers = int(2 * nw - 1)
    
    # Generate DPSS tapers
    tapers, eigenvalues = signal.windows.dpss(n_samples, nw, k_tapers, 
                                               return_ratios=True)
    
    # Compute power spectral density for each component
    h_psd = compute_multitaper_psd(h_component, tapers, sampling_rate)
    d_psd = compute_multitaper_psd(d_component, tapers, sampling_rate)
    z_psd = compute_multitaper_psd(z_component, tapers, sampling_rate)
    
    # Target frequency band: 0.095 - 0.110 Hz
    freq_min, freq_max = 0.095, 0.110
    
    # Integrate power in target frequency band
    h_power = integrate_power_in_band(h_psd, freq_min, freq_max, sampling_rate)
    d_power = integrate_power_in_band(d_psd, freq_min, freq_max, sampling_rate)
    z_power = integrate_power_in_band(z_psd, freq_min, freq_max, sampling_rate)
    
    # Calculate polarization ratio
    horizontal_power = np.sqrt(h_power**2 + d_power**2)
    pr = horizontal_power / z_power if z_power > 0 else 0
    
    return pr


def compute_multitaper_psd(data, tapers, sampling_rate):
    """
    Compute power spectral density using multitaper method.
    """
    n_tapers = tapers.shape[0]
    n_fft = len(data)
    
    # Apply each taper and compute FFT
    psds = []
    for taper in tapers:
        windowed = data * taper
        fft_result = np.fft.fft(windowed, n=n_fft)
        psd = np.abs(fft_result)**2
        psds.append(psd)
    
    # Average across tapers
    avg_psd = np.mean(psds, axis=0)
    
    # Normalize by sampling rate
    avg_psd = avg_psd / sampling_rate
    
    return avg_psd


def integrate_power_in_band(psd, freq_min, freq_max, sampling_rate):
    """
    Integrate power spectral density in specified frequency band.
    """
    n_fft = len(psd)
    freqs = np.fft.fftfreq(n_fft, d=sampling_rate)
    
    # Find indices corresponding to frequency band
    band_indices = np.where((freqs >= freq_min) & (freqs <= freq_max))[0]
    
    # Integrate power in band
    power = np.sum(psd[band_indices])
    
    return power
```

---

## 2. Anomaly Detection using Extreme Value Theory (EVT)

```python
def detect_anomalies_evt(pr_values, baseline_days=30, percentile=95):
    """
    Detect anomalies using Extreme Value Theory (EVT).
    
    Parameters:
    -----------
    pr_values : array-like
        Polarization Ratio time series
    baseline_days : int
        Number of days for baseline calculation
    percentile : float
        Percentile threshold (default: 95)
    
    Returns:
    --------
    anomalies : array-like (bool)
        Boolean array indicating anomaly positions
    threshold : float
        EVT-derived threshold value
    """
    # Extract baseline data (last N days)
    baseline_data = pr_values[-baseline_days * 24:]  # Assuming hourly data
    
    # Fit Generalized Extreme Value (GEV) distribution
    shape, loc, scale = genextreme.fit(baseline_data)
    
    # Calculate threshold at specified percentile
    threshold = genextreme.ppf(percentile / 100.0, shape, loc, scale)
    
    # Identify anomalies
    anomalies = pr_values > threshold
    
    return anomalies, threshold


def extract_anomaly_periods(times, pr_values, anomalies):
    """
    Extract continuous anomaly periods from boolean array.
    
    Returns:
    --------
    periods : list of dict
        List of anomaly periods with start, end, max_pr
    """
    periods = []
    in_anomaly = False
    start_idx = None
    
    for i, is_anomaly in enumerate(anomalies):
        if is_anomaly and not in_anomaly:
            # Start of new anomaly period
            start_idx = i
            in_anomaly = True
        elif not is_anomaly and in_anomaly:
            # End of anomaly period
            end_idx = i - 1
            max_pr = np.max(pr_values[start_idx:end_idx+1])
            periods.append({
                'start_time': times[start_idx],
                'end_time': times[end_idx],
                'max_pr': max_pr,
                'duration_hours': end_idx - start_idx + 1
            })
            in_anomaly = False
    
    # Handle case where anomaly extends to end of data
    if in_anomaly:
        end_idx = len(anomalies) - 1
        max_pr = np.max(pr_values[start_idx:end_idx+1])
        periods.append({
            'start_time': times[start_idx],
            'end_time': times[end_idx],
            'max_pr': max_pr,
            'duration_hours': end_idx - start_idx + 1
        })
    
    return periods
```

---

## 3. Earthquake Correlation - Python

```python
from geopy.distance import geodesic
from datetime import datetime, timedelta

def correlate_with_earthquakes(anomaly_date, station_lat, station_lon, 
                                 earthquakes, max_distance_km=200, 
                                 max_days_after=14):
    """
    Correlate anomaly with subsequent earthquakes.
    
    Parameters:
    -----------
    anomaly_date : datetime
        Date of detected anomaly
    station_lat, station_lon : float
        Station coordinates
    earthquakes : list of dict
        Earthquake events with 'time', 'lat', 'lon', 'magnitude'
    max_distance_km : float
        Maximum distance for correlation (default: 200 km)
    max_days_after : int
        Maximum days after anomaly to search (default: 14)
    
    Returns:
    --------
    correlation : dict or None
        Correlation details if found, None otherwise
    """
    # Define time window
    window_start = anomaly_date
    window_end = anomaly_date + timedelta(days=max_days_after)
    
    # Find earthquakes within time and space window
    correlated_events = []
    
    for eq in earthquakes:
        eq_time = datetime.fromisoformat(eq['time'])
        
        # Check temporal criteria
        if not (window_start <= eq_time <= window_end):
            continue
        
        # Check spatial criteria
        distance_km = geodesic(
            (station_lat, station_lon),
            (eq['lat'], eq['lon'])
        ).kilometers
        
        if distance_km <= max_distance_km:
            days_after = (eq_time - anomaly_date).days
            correlated_events.append({
                'earthquake_time': eq_time,
                'magnitude': eq['magnitude'],
                'distance_km': distance_km,
                'days_after_anomaly': days_after,
                'location': eq.get('place', 'Unknown'),
                'depth_km': eq.get('depth', None)
            })
    
    # Return strongest correlation (highest magnitude, closest distance)
    if correlated_events:
        # Sort by magnitude (descending), then distance (ascending)
        correlated_events.sort(key=lambda x: (-x['magnitude'], x['distance_km']))
        return correlated_events[0]
    
    return None


def classify_detection(anomaly_detected, earthquake_occurred):
    """
    Classify detection as TP, FP, or FN.
    
    Parameters:
    -----------
    anomaly_detected : bool
        Whether anomaly was detected
    earthquake_occurred : bool
        Whether earthquake occurred within window
    
    Returns:
    --------
    classification : str
        'TP', 'FP', or 'FN'
    """
    if anomaly_detected and earthquake_occurred:
        return 'TP'  # True Positive
    elif anomaly_detected and not earthquake_occurred:
        return 'FP'  # False Positive
    elif not anomaly_detected and earthquake_occurred:
        return 'FN'  # False Negative
    else:
        return 'TN'  # True Negative (normal case)
```

---

## 4. Data Aggregation - Python

```python
import json
from pathlib import Path
from datetime import datetime

def aggregate_station_data(date, stations, output_dir):
    """
    Aggregate all station data for a specific date into single JSON file.
    
    Parameters:
    -----------
    date : str
        Date in YYYY-MM-DD format
    stations : list
        List of station codes
    output_dir : Path
        Output directory for aggregated file
    
    Returns:
    --------
    aggregated_file : Path
        Path to created aggregated JSON file
    """
    aggregated_data = {
        'date': date,
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'stations': {},
        'earthquake_correlations': {},
        'metadata': {}
    }
    
    # Load data for each station
    for station in stations:
        station_file = output_dir / 'data' / f'{station}_{date}.json'
        
        if station_file.exists():
            with open(station_file, 'r') as f:
                station_data = json.load(f)
                aggregated_data['stations'][station] = station_data
        
        # Load earthquake correlations
        eq_file = output_dir / 'data' / f'{station}_earthquakes_{date}.json'
        if eq_file.exists():
            with open(eq_file, 'r') as f:
                eq_data = json.load(f)
                aggregated_data['earthquake_correlations'][station] = eq_data
    
    # Load station metadata
    metadata_file = output_dir / 'data' / 'stations.json'
    if metadata_file.exists():
        with open(metadata_file, 'r') as f:
            aggregated_data['metadata'] = json.load(f)
    
    # Write aggregated file
    output_file = output_dir / 'data' / f'aggregated_{date}.json'
    with open(output_file, 'w') as f:
        json.dump(aggregated_data, f, indent=2)
    
    print(f"Created aggregated file: {output_file}")
    return output_file
```

---

## 5. Frontend Map Visualization - JavaScript

```javascript
// Initialize Leaflet map
function initializeMap() {
    const map = L.map('map-container').setView([20, 0], 2);
    
    // Add OpenStreetMap tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 18
    }).addTo(map);
    
    return map;
}

// Add station markers to map
function addStationMarkers(map, stationsData, earthquakeData) {
    const markers = {};
    
    Object.keys(stationsData).forEach(stationCode => {
        const station = stationsData[stationCode];
        const lat = station.latitude;
        const lon = station.longitude;
        
        // Determine marker color based on status
        let markerColor = 'gray';  // Normal
        let status = 'Normal';
        
        if (station.is_anomalous) {
            const hasEarthquake = earthquakeData[stationCode] && 
                                   earthquakeData[stationCode].length > 0;
            
            if (hasEarthquake) {
                markerColor = 'orange';  // True Positive
                status = 'True Positive';
            } else {
                markerColor = 'red';  // False Positive
                status = 'False Positive';
            }
        }
        
        // Create marker icon
        const icon = L.divIcon({
            className: 'custom-marker',
            html: `<div style="background-color: ${markerColor}; 
                               width: 12px; height: 12px; 
                               border-radius: 50%; 
                               border: 2px solid white;"></div>`,
            iconSize: [12, 12]
        });
        
        // Create marker
        const marker = L.marker([lat, lon], { icon: icon });
        
        // Create popup content
        let popupContent = `
            <strong>${stationCode}</strong><br>
            ${station.name}<br>
            ${station.country}<br>
            Lat: ${lat.toFixed(2)}, Lon: ${lon.toFixed(2)}<br>
            <strong>Status:</strong> ${status}
        `;
        
        // Add earthquake details if TP
        if (status === 'True Positive' && earthquakeData[stationCode]) {
            const eq = earthquakeData[stationCode][0];
            popupContent += `
                <hr>
                <strong>Earthquake:</strong><br>
                Magnitude: M${eq.magnitude}<br>
                Distance: ${eq.distance_km.toFixed(1)} km<br>
                Location: ${eq.location}<br>
                Days After Anomaly: ${eq.days_after}
            `;
        }
        
        marker.bindPopup(popupContent);
        
        // Add 200km radius circle on hover
        let circle = null;
        marker.on('mouseover', function() {
            circle = L.circle([lat, lon], {
                radius: 200000,  // 200 km in meters
                color: markerColor,
                fillOpacity: 0.1,
                weight: 1
            }).addTo(map);
        });
        
        marker.on('mouseout', function() {
            if (circle) {
                map.removeLayer(circle);
                circle = null;
            }
        });
        
        marker.addTo(map);
        markers[stationCode] = marker;
    });
    
    return markers;
}
```

---

## 6. Frontend Chart Visualization - JavaScript

```javascript
// Create 7-Day Anomaly Trend Chart
function create7DayTrendChart(dates, anomalyCounts) {
    const ctx = document.getElementById('trend-chart').getContext('2d');
    
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [{
                label: 'Anomalies Detected',
                data: anomalyCounts,
                borderColor: 'rgb(255, 99, 132)',
                backgroundColor: 'rgba(255, 99, 132, 0.1)',
                tension: 0.3,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                title: {
                    display: true,
                    text: '7-Day Anomaly Trend'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1
                    }
                }
            }
        }
    });
}

// Create Station Status Doughnut Chart
function createStationStatusChart(normalCount, tpCount, fpCount) {
    const ctx = document.getElementById('status-chart').getContext('2d');
    
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Normal', 'With Earthquake (TP)', 'False Alarm (FP)'],
            datasets: [{
                data: [normalCount, tpCount, fpCount],
                backgroundColor: [
                    'rgb(128, 128, 128)',  // Gray
                    'rgb(255, 159, 64)',   // Orange
                    'rgb(255, 99, 132)'    // Red
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom'
                },
                title: {
                    display: true,
                    text: 'Station Status Distribution'
                }
            }
        }
    });
}
```

---

**Document Version**: 1.0  
**Last Updated**: February 5, 2026  
**Author**: Nur Syaiful Afrizal  
**License**: Copyright © 2026 Universiti Putra Malaysia
