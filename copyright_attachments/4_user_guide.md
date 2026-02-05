# GEMPRA User Guide

## Introduction

Welcome to GEMPRA (Geomagnetic Earthquake Monitoring Platform using Polarization Ratio Analysis). This guide will help you navigate and utilize the platform effectively.

**Platform URL**: https://syaifulafrizal.github.io/global-pra-observation/

---

## Dashboard Overview

### Main Interface Components

```
┌─────────────────────────────────────────────────────────────┐
│                    GEMPRA Header                             │
│  🌋 GEMPRA                                                   │
│  Geomagnetic Earthquake Monitoring using PRA                │
│  [Date Selector ▼] [Dark Mode Toggle]                       │
└─────────────────────────────────────────────────────────────┘
│                                                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ Active   │ │Anomalies │ │ Events   │ │  False   │       │
│  │Stations  │ │Detected  │ │  (24h)   │ │Positives │       │
│  │   51     │ │    0     │ │    0     │ │    0     │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐│
│  │         Data Availability Report                         ││
│  │  Stations Available: 51/51 (100%)                        ││
│  │  Data Source: Standard                                   ││
│  └─────────────────────────────────────────────────────────┘│
│                                                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 7-Day    │ │ Station  │ │Detection │ │Magnitude │       │
│  │ Trend    │ │ Status   │ │ Success  │ │  Dist.   │       │
│  │ [Chart]  │ │ [Chart]  │ │ [Chart]  │ │ [Chart]  │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              Interactive Station Map                     ││
│  │  [Global map with station markers]                       ││
│  │  Legend: 🔺Gray=Normal 🔺Orange=TP 🔺Red=FP              ││
│  └─────────────────────────────────────────────────────────┘│
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              Station Analysis                            ││
│  │  Select Station: [Dropdown ▼]                            ││
│  │  [PRA Analysis Plot]                                     ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

---

## Feature Guide

### 1. Date Selection

**Location**: Top right of header

**How to Use**:
1. Click the date dropdown menu
2. Select from available dates (last 7 days)
3. Dashboard automatically updates with selected date's data

**Date Labels**:
- **(Today)** - Current day's data
- **(Yesterday)** - Previous day's data
- **Date only** - Historical data

### 2. Dark/Light Mode Toggle

**Location**: Top right, next to date selector

**How to Use**:
- Click the toggle switch to switch between modes
- Setting is saved in browser localStorage
- Automatically applied on next visit

**Benefits**:
- **Light Mode**: Better for daytime viewing
- **Dark Mode**: Reduced eye strain in low-light conditions

### 3. Summary Statistics Cards

**Metrics Displayed**:

#### Active Stations
- **Value**: Number of stations with data
- **Description**: Total monitored stations
- **Typical Range**: 45-51 stations

#### Anomalies Detected
- **Value**: Number of PRA anomalies
- **Description**: Polarization ratio anomalies detected
- **Color**: Orange if > 0

#### Events (24h)
- **Value**: Global earthquakes M≥5.0
- **Description**: USGS earthquake count
- **Scope**: Worldwide, last 24 hours

#### False Positives
- **Value**: Anomalies without earthquakes
- **Description**: False alarms
- **Calculation**: Anomalies - True Positives

#### False Negatives
- **Value**: Missed earthquakes
- **Description**: Earthquakes without prior anomalies
- **Window**: 14-day lookback

### 4. Data Availability Report

**Information Shown**:
- **Stations Available**: Fraction with data (e.g., 51/51)
- **Coverage Percentage**: Data availability %
- **Data Source**: Standard or Hybrid (with fallback)
- **Processing Date**: Analysis window date

**Status Icons**:
- ✅ Green: >90% coverage
- ⚠️ Yellow: 50-90% coverage
- ⚠️ Red: <50% coverage

### 5. Analytical Charts

#### 7-Day Anomaly Trend
- **Type**: Line chart
- **X-axis**: Date (last 7 days)
- **Y-axis**: Number of anomalies
- **Purpose**: Identify temporal patterns

#### Station Status
- **Type**: Doughnut chart
- **Categories**: Normal, With EQ, False Alarm
- **Purpose**: Overall system status

#### Detection Success Rate
- **Type**: Gauge/pie chart
- **Metric**: TP / (TP + FN) × 100%
- **Purpose**: Method validation

#### Magnitude Distribution
- **Type**: Horizontal bar chart
- **Categories**: M5.0-6.0, M6.0-7.0, M7.0+, M8+
- **Purpose**: Earthquake severity distribution

### 6. Interactive Station Map

**Features**:
- **Global Coverage**: All 51 stations displayed
- **Marker Colors**:
  - 🔺 **Gray**: Normal (no anomaly)
  - 🔺 **Orange**: True Positive (anomaly + earthquake)
  - 🔺 **Red**: False Positive (anomaly, no earthquake)
- **Hover Effect**: 200km radius circle appears on hover
- **Click Interaction**: Opens detailed popup

**Popup Information**:
- Station code and name
- Country and coordinates
- Anomaly status
- Earthquake correlation details (if applicable)
  - Magnitude
  - Distance
  - Location
  - Days before anomaly

**Map Controls**:
- **Zoom**: Mouse wheel or +/- buttons
- **Pan**: Click and drag
- **Reset**: Double-click to reset view

### 7. Station Analysis Panel

**How to Use**:
1. Select station from dropdown
2. View PRA analysis plot
3. Examine time series data

**Plot Information**:
- **X-axis**: Time (20:00 - 04:00 local)
- **Y-axis**: Polarization Ratio
- **Red Line**: EVT threshold
- **Blue Line**: Measured PR values
- **Shaded Area**: Anomaly periods

### 8. Download Anomalies

**Location**: "Download Anomalies" button above map

**How to Use**:
1. Click the download button
2. CSV file automatically downloads
3. Filename: `anomalies_YYYY-MM-DD.csv`

**CSV Contents**:
- Station code
- Date and time
- Polarization ratio values
- Threshold values
- Anomaly status

---

## Interpretation Guide

### Understanding Anomaly Status

#### True Positive (TP)
- **Meaning**: Anomaly correctly predicted earthquake
- **Criteria**: 
  - Anomaly detected
  - M≥5.0 earthquake within 14 days and 200km
- **Interpretation**: Successful precursor detection

#### False Positive (FP)
- **Meaning**: Anomaly without subsequent earthquake
- **Criteria**:
  - Anomaly detected
  - No M≥5.0 earthquake within 14 days and 200km
- **Interpretation**: False alarm or unrelated disturbance

#### False Negative (FN)
- **Meaning**: Earthquake occurred without prior anomaly
- **Criteria**:
  - M≥5.0 earthquake occurred
  - No anomaly detected 0-14 days before
- **Interpretation**: Missed precursor signal

### Reading the Map

**Station Clustering**:
- **Dense Areas**: Multiple nearby stations (e.g., Europe, Japan)
- **Sparse Areas**: Limited coverage (e.g., oceans, remote regions)

**Anomaly Patterns**:
- **Isolated Anomalies**: Single station detection
- **Clustered Anomalies**: Multiple nearby stations (stronger signal)

---

## Tips & Best Practices

### For Researchers

1. **Compare Multiple Dates**: Use date selector to track temporal evolution
2. **Cross-Reference Stations**: Check nearby stations for corroboration
3. **Download Data**: Export CSV for offline analysis
4. **Monitor Trends**: Use 7-day chart to identify patterns

### For Students

1. **Explore Different Stations**: Click various markers to learn geography
2. **Understand Metrics**: Read popup details to grasp correlation logic
3. **Compare TP/FP/FN**: Learn about method validation
4. **Use Dark Mode**: Easier for extended viewing sessions

### For General Public

1. **Check Daily Updates**: Platform refreshes daily
2. **Focus on TP Markers**: Orange markers show successful predictions
3. **Read Earthquake Details**: Click markers for event information
4. **Understand Limitations**: 14-day window, M≥5.0 threshold

---

## Troubleshooting

### Common Issues

#### "No Data Available"
- **Cause**: Selected date has no processed data
- **Solution**: Choose a different date from dropdown

#### Map Not Loading
- **Cause**: Slow internet or browser issue
- **Solution**: Refresh page, check connection

#### Charts Not Displaying
- **Cause**: JavaScript disabled or ad blocker
- **Solution**: Enable JavaScript, disable ad blockers

#### Station Plot Not Showing
- **Cause**: No plot available for selected date
- **Solution**: Try different station or date

---

## Frequently Asked Questions (FAQ)

**Q: How often is data updated?**  
A: Daily, typically around 6 AM UTC.

**Q: Why are some dates missing?**  
A: Only last 7 days are retained for performance.

**Q: Can I access historical data?**  
A: Historical archives are available upon request.

**Q: What does "Hybrid" data source mean?**  
A: Some stations use fallback data from previous days.

**Q: Why M≥5.0 threshold?**  
A: Focus on significant earthquakes with measurable precursors.

**Q: Is this an early warning system?**  
A: No, this is a research platform for method validation.

---

## Contact & Support

**Developer**: Nur Syaiful Afrizal  
**Institution**: Universiti Putra Malaysia  
**GitHub**: https://github.com/syaifulafrizal  
**Issues**: Report via GitHub Issues

---

**Document Version**: 1.0  
**Last Updated**: February 5, 2026
