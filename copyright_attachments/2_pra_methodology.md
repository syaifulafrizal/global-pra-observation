# Polarization Ratio Analysis (PRA) Methodology

## Scientific Background

Polarization Ratio Analysis (PRA) is a novel methodology for detecting earthquake precursors through geomagnetic field analysis. This technique analyzes the ratio of horizontal to vertical magnetic field components to identify anomalous patterns that may precede seismic events.

---

## Theoretical Foundation

### Geomagnetic Field Components

The Earth's magnetic field is measured in three orthogonal components:

- **H (Horizontal)**: North-South component
- **D (Declination)**: East-West component  
- **Z (Vertical)**: Vertical component

### Polarization Ratio

The PRA methodology calculates:

```
PR = √(H² + D²) / Z
```

Where:

- PR = Polarization Ratio
- H = Horizontal magnetic field intensity
- D = Declination component
- Z = Vertical magnetic field intensity

---

## Processing Pipeline

### 1. Data Acquisition

- **Source**: INTERMAGNET network stations
- **Sampling Rate**: 1-minute resolution
- **Components**: H, D, Z magnetic field vectors

### 2. Time Window Selection

- **Analysis Window**: 20:00 - 04:00 local time
- **Rationale**: Reduced anthropogenic noise during nighttime
- **Duration**: 8-hour continuous window

### 3. Spectral Analysis

#### Multitaper Method (MTM)

- **Time-Bandwidth Product (NW)**: 3.5
- **Number of Tapers**: 2*NW - 1 = 6
- **Purpose**: Optimal spectral estimation with reduced variance

#### Frequency Band Selection

- **Target Band**: 0.095 - 0.110 Hz
- **Rationale**: Ultra-Low Frequency (ULF) range associated with seismo-electromagnetic phenomena
- **Period**: ~9-10 seconds

### 4. Polarization Ratio Calculation

For each time window:

```python
# Pseudocode
for each_night_window:
    H_spectrum = multitaper_spectrum(H_component, NW=3.5)
    D_spectrum = multitaper_spectrum(D_component, NW=3.5)
    Z_spectrum = multitaper_spectrum(Z_component, NW=3.5)

    # Extract power in target frequency band
    H_power = integrate(H_spectrum, 0.095, 0.110)
    D_power = integrate(D_spectrum, 0.095, 0.110)
    Z_power = integrate(Z_spectrum, 0.095, 0.110)

    # Calculate polarization ratio
    PR = sqrt(H_power² + D_power²) / Z_power
```

### 5. Anomaly Detection

#### Extreme Value Theory (EVT)

- **Method**: Generalized Extreme Value (GEV) distribution
- **Baseline**: 30-day historical data
- **Threshold**: 95th percentile of GEV distribution

#### Anomaly Criteria

An anomaly is detected when:

```
PR(t) > Threshold_EVT
```

Where:

- PR(t) = Polarization ratio at time t
- Threshold_EVT = Statistical threshold from EVT analysis

---

## Earthquake Correlation

### Spatial Criteria

- **Radius**: 200 km from station location
- **Method**: Geodesic distance calculation (Haversine formula)

### Temporal Criteria

- **Window**: 0-14 days after anomaly detection
- **Rationale**: Precursor phenomena typically occur days to weeks before earthquakes

### Magnitude Threshold

- **Minimum**: M ≥ 5.0
- **Rationale**: Focus on significant seismic events with measurable precursors

---

## Classification System

### True Positive (TP)

- **Definition**: Anomaly detected AND earthquake occurred within 14 days and 200 km
- **Interpretation**: Successful precursor detection

### False Positive (FP)

- **Definition**: Anomaly detected BUT no earthquake within 14 days and 200 km
- **Interpretation**: False alarm or unrelated geomagnetic disturbance

### False Negative (FN)

- **Definition**: Earthquake occurred BUT no anomaly detected 0-14 days prior
- **Interpretation**: Missed precursor signal

---

## Statistical Validation

### Performance Metrics

```
Precision = TP / (TP + FP)
Recall = TP / (TP + FN)
F1-Score = 2 * (Precision * Recall) / (Precision + Recall)
```

### Success Rate Calculation

```
Detection Rate = (TP / Total Earthquakes) * 100%
False Alarm Rate = (FP / Total Anomalies) * 100%
```

---

## Novel Contributions

1. **Automated Processing**: Fully automated pipeline from data acquisition to correlation
2. **Multi-Station Network**: Global coverage with 51+ stations
3. **Real-Time Analysis**: Daily updates with latest data
4. **Statistical Rigor**: EVT-based thresholding for objective anomaly detection
5. **Comprehensive Tracking**: TP/FP/FN classification for method validation

---

## Limitations & Future Work

### Current Limitations

- Regional variations in geomagnetic baseline
- Influence of solar activity and magnetic storms
- Limited to M ≥ 5.0 earthquakes
- 14-day prediction window (broad temporal resolution)

### Future Enhancements

- Machine learning integration for pattern recognition
- Multi-parameter analysis (combining with ionospheric data)
- Refined temporal prediction windows
- Real-time alerting system

---

## References

1. Hayakawa, M., et al. (2007). "Monitoring of ULF electromagnetic emissions before earthquakes"
2. Molchanov, O., & Hayakawa, M. (2008). "Seismo-electromagnetics and related phenomena"
3. Fraser-Smith, A. C., et al. (1990). "Low-frequency magnetic field measurements near the epicenter of the Ms 7.1 Loma Prieta earthquake"
