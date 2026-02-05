# GEMPRA System Architecture Documentation

## Overview
This document describes the technical architecture of the GEMPRA (Geomagnetic Earthquake Monitoring Platform using Polarization Ratio Analysis) system.

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GEMPRA PLATFORM                              │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES LAYER                            │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐              ┌──────────────────┐            │
│  │   INTERMAGNET    │              │   USGS API       │            │
│  │   51+ Stations   │              │  Earthquake DB   │            │
│  │  (Geomagnetic)   │              │   (M ≥ 5.0)      │            │
│  └────────┬─────────┘              └────────┬─────────┘            │
└───────────┼──────────────────────────────────┼──────────────────────┘
            │                                  │
            ▼                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    BACKEND PROCESSING LAYER                          │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              Data Acquisition Module (Python)                 │  │
│  │  • Automated daily downloads                                  │  │
│  │  • Multi-station parallel processing                          │  │
│  │  • Data validation & quality control                          │  │
│  └───────────────────────┬──────────────────────────────────────┘  │
│                          ▼                                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │         Signal Processing Module (Python/NumPy/SciPy)         │  │
│  │  • Multitaper Spectral Analysis (NW=3.5)                      │  │
│  │  • Frequency band filtering (0.095-0.110 Hz)                  │  │
│  │  • Time window extraction (20:00-04:00 local)                 │  │
│  │  • Polarization Ratio Analysis (PRA)                          │  │
│  └───────────────────────┬──────────────────────────────────────┘  │
│                          ▼                                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │          Anomaly Detection Module (Python/Pandas)             │  │
│  │  • Extreme Value Theory (EVT) thresholding                    │  │
│  │  • Statistical anomaly identification                         │  │
│  │  • Temporal pattern analysis                                  │  │
│  └───────────────────────┬──────────────────────────────────────┘  │
│                          ▼                                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │      Earthquake Correlation Module (Python/Geopy)             │  │
│  │  • USGS API integration                                       │  │
│  │  • Geospatial distance calculation (200km radius)             │  │
│  │  • Temporal correlation (14-day window)                       │  │
│  │  • TP/FP/FN classification                                    │  │
│  └───────────────────────┬──────────────────────────────────────┘  │
│                          ▼                                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │           Data Aggregation Module (Python)                    │  │
│  │  • JSON file generation per station/date                      │  │
│  │  • Hybrid aggregation (98% request reduction)                 │  │
│  │  • Historical data persistence                                │  │
│  │  • 7-day rolling window management                            │  │
│  └───────────────────────┬──────────────────────────────────────┘  │
└────────────────────────────┼────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      DATA STORAGE LAYER                              │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │ Station JSON │  │ Aggregated   │  │  Historical  │             │
│  │   Files      │  │  Data Files  │  │   Archives   │             │
│  │ (Per Date)   │  │ (Per Date)   │  │   (CSV/JSON) │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
└─────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   DEPLOYMENT & CI/CD LAYER                           │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              GitHub Actions Workflow                          │  │
│  │  • Automated daily processing                                 │  │
│  │  • Data preparation & aggregation                             │  │
│  │  • Static site generation                                     │  │
│  │  • Deployment to GitHub Pages                                 │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FRONTEND PRESENTATION LAYER                       │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │           Web Application (HTML/CSS/JavaScript)               │  │
│  │                                                                │  │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐ │  │
│  │  │  Interactive   │  │  Data Viz      │  │  Station       │ │  │
│  │  │  Map           │  │  Charts        │  │  Analysis      │ │  │
│  │  │  (Leaflet.js)  │  │  (Chart.js)    │  │  Plots         │ │  │
│  │  └────────────────┘  └────────────────┘  └────────────────┘ │  │
│  │                                                                │  │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐ │  │
│  │  │  Date          │  │  Dark/Light    │  │  Summary       │ │  │
│  │  │  Selector      │  │  Mode Toggle   │  │  Statistics    │ │  │
│  │  └────────────────┘  └────────────────┘  └────────────────┘ │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          END USERS                                   │
├─────────────────────────────────────────────────────────────────────┤
│  • Researchers                                                       │
│  • Students                                                          │
│  • Geophysics Community                                              │
│  • Public Access via Web Browser                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Data Sources
- **INTERMAGNET Network**: 51+ global magnetometer stations
- **USGS Earthquake Database**: Real-time earthquake data (M ≥ 5.0)

### 2. Backend Processing
- **Language**: Python 3.x
- **Key Libraries**: NumPy, SciPy, Pandas, Geopy
- **Processing Pipeline**:
  1. Data acquisition and validation
  2. Signal processing (Multitaper, PRA)
  3. Anomaly detection (EVT)
  4. Earthquake correlation
  5. Data aggregation and export

### 3. Data Storage
- **Format**: JSON (primary), CSV (historical)
- **Structure**: Date-specific files, aggregated datasets
- **Retention**: 7-day rolling window + historical archives

### 4. Deployment
- **Platform**: GitHub Pages (static hosting)
- **CI/CD**: GitHub Actions (automated workflows)
- **Update Frequency**: Daily automated processing

### 5. Frontend
- **Technologies**: HTML5, CSS3, JavaScript (ES6+)
- **Libraries**: Leaflet.js (maps), Chart.js (visualizations)
- **Features**: Responsive design, dark/light modes, interactive elements

---

## Data Flow

```
Raw Data → Processing → Anomaly Detection → Correlation → Aggregation → Web Display
```

### Detailed Flow:
1. **Acquisition**: Download geomagnetic data from INTERMAGNET
2. **Processing**: Apply PRA methodology and spectral analysis
3. **Detection**: Identify anomalies using EVT thresholds
4. **Correlation**: Match anomalies with USGS earthquakes (200km, 14-day window)
5. **Classification**: Categorize as TP/FP/FN
6. **Aggregation**: Combine data into optimized JSON files
7. **Deployment**: Push to GitHub Pages
8. **Visualization**: Render interactive dashboard for users

---

## Performance Optimizations

1. **Hybrid Aggregation**: 98% reduction in network requests (350+ → 7)
2. **Lazy Loading**: Load station data on-demand
3. **Caching**: Browser-side caching for static assets
4. **Compression**: Minified JavaScript and CSS
5. **CDN**: Leveraging GitHub Pages CDN for global distribution

---

## Security & Reliability

- **Data Validation**: Input sanitization and type checking
- **Error Handling**: Graceful degradation with fallback data
- **Version Control**: Git-based change tracking
- **Backup**: Historical data archives
- **Monitoring**: Automated deployment logs

---

**Document Version**: 1.0  
**Last Updated**: February 5, 2026  
**Author**: Nur Syaiful Afrizal
