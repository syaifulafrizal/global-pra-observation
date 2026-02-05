# Screenshot Instructions for Copyright Application

Since the automated browser tool is currently unavailable, you'll need to manually capture screenshots of the GEMPRA platform. Follow these instructions to gather all necessary visual evidence.

---

## 🌐 Platform URL
**https://syaifulafrizal.github.io/global-pra-observation/**

---

## 📸 Required Screenshots

### 1. Main Dashboard - Light Mode
**Filename**: `screenshot_01_dashboard_light.png`

**Instructions**:
1. Open the GEMPRA platform in your browser
2. Ensure you're in **Light Mode** (toggle if needed)
3. Select a recent date that has data (preferably today or yesterday)
4. Wait for all components to load:
   - Summary statistics cards
   - Data availability report
   - All 4 charts (7-Day Trend, Station Status, Detection Success, Magnitude Distribution)
   - Interactive map
5. Take a **full-page screenshot** (use browser extension or F12 > Ctrl+Shift+P > "Capture full size screenshot" in Chrome)

**What to capture**: Entire dashboard from header to footer

---

### 2. Main Dashboard - Dark Mode
**Filename**: `screenshot_02_dashboard_dark.png`

**Instructions**:
1. Click the **Dark Mode toggle** (top right, next to date selector)
2. Ensure all elements have switched to dark theme
3. Take a **full-page screenshot**

**What to capture**: Same view as screenshot 1, but in dark theme

---

### 3. Interactive Map - Global View
**Filename**: `screenshot_03_map_global.png`

**Instructions**:
1. Scroll to the **Interactive Station Map** section
2. Zoom out to show **all 51 stations globally**
3. Ensure the legend is visible (Gray/Orange/Red markers)
4. Take a screenshot of the map area

**What to capture**: Full map showing global station distribution

---

### 4. Interactive Map - Station Hover
**Filename**: `screenshot_04_map_hover.png`

**Instructions**:
1. **Hover** your mouse over any station marker
2. The **200km radius circle** should appear around the station
3. Take a screenshot while hovering (before clicking)

**What to capture**: Map with visible 200km radius circle

---

### 5. Interactive Map - Station Popup (True Positive)
**Filename**: `screenshot_05_map_popup_tp.png`

**Instructions**:
1. **Click** on an **Orange marker** (True Positive - anomaly with earthquake)
2. The popup should show:
   - Station code and name
   - Anomaly status
   - Earthquake correlation details (magnitude, distance, location, days before)
3. Take a screenshot with the popup open

**What to capture**: Map with detailed popup showing TP correlation

---

### 6. Interactive Map - Station Popup (False Positive)
**Filename**: `screenshot_06_map_popup_fp.png`

**Instructions**:
1. **Click** on a **Red marker** (False Positive - anomaly without earthquake)
2. The popup should show anomaly status without earthquake details
3. Take a screenshot with the popup open

**What to capture**: Map with popup showing FP status

---

### 7. Station Analysis Plot - Anomaly Example
**Filename**: `screenshot_07_station_plot_anomaly.png`

**Instructions**:
1. Scroll to the **Station Analysis** section at the bottom
2. Select a station from the dropdown that has an **anomaly** (check map for orange/red markers)
3. Wait for the PRA plot to load
4. The plot should show:
   - Blue line (Polarization Ratio values)
   - Red horizontal line (EVT threshold)
   - Time axis (20:00 - 04:00)
   - Shaded areas where PR exceeds threshold
5. Take a screenshot of the plot

**What to capture**: PRA analysis plot showing anomaly detection

---

### 8. Station Analysis Plot - Normal Example
**Filename**: `screenshot_08_station_plot_normal.png`

**Instructions**:
1. Select a **different station** with **no anomaly** (gray marker on map)
2. Wait for the plot to load
3. The plot should show PR values below threshold
4. Take a screenshot

**What to capture**: PRA plot showing normal (non-anomalous) behavior

---

### 9. Charts Close-up - 7-Day Trend
**Filename**: `screenshot_09_chart_7day.png`

**Instructions**:
1. Scroll to the **7-Day Anomaly Trend** chart (top left of charts section)
2. Take a close-up screenshot of just this chart
3. Ensure the chart shows the line graph with dates on X-axis

**What to capture**: 7-Day Anomaly Trend chart only

---

### 10. Charts Close-up - Station Status
**Filename**: `screenshot_10_chart_status.png`

**Instructions**:
1. Take a close-up screenshot of the **Station Status** doughnut chart (top right)
2. Ensure legend is visible (Normal, With EQ, False Alarm)

**What to capture**: Station Status doughnut chart only

---

### 11. Charts Close-up - Detection Success
**Filename**: `screenshot_11_chart_success.png`

**Instructions**:
1. Take a close-up screenshot of the **Detection Success Rate** chart (bottom left)

**What to capture**: Detection Success Rate chart only

---

### 12. Charts Close-up - Magnitude Distribution
**Filename**: `screenshot_12_chart_magnitude.png`

**Instructions**:
1. Take a close-up screenshot of the **Magnitude Distribution** bar chart (bottom right)
2. Ensure all magnitude categories are visible (M5-6, M6-7, M7-8, M8+)

**What to capture**: Magnitude Distribution chart only

---

### 13. Data Availability Report
**Filename**: `screenshot_13_data_availability.png`

**Instructions**:
1. Scroll to the **Data Availability Report** section (below summary cards)
2. Take a screenshot showing:
   - Stations Available count
   - Coverage percentage
   - Data Source (Standard/Hybrid)
   - Processing Date

**What to capture**: Data Availability Report box

---

### 14. Mobile Responsive View (Optional)
**Filename**: `screenshot_14_mobile.png`

**Instructions**:
1. Open browser DevTools (F12)
2. Toggle **Device Toolbar** (Ctrl+Shift+M)
3. Select a mobile device (e.g., iPhone 12 Pro)
4. Take a screenshot of the responsive layout

**What to capture**: Dashboard on mobile viewport

---

## 💾 Saving Screenshots

### Recommended Format:
- **Format**: PNG (lossless, best quality)
- **Resolution**: Native screen resolution (don't resize)
- **Location**: Save to `c:\Users\SYAIFUL\Downloads\pra-observation\copyright_attachments\screenshots\`

### File Organization:
```
copyright_attachments/
├── screenshots/
│   ├── screenshot_01_dashboard_light.png
│   ├── screenshot_02_dashboard_dark.png
│   ├── screenshot_03_map_global.png
│   ├── screenshot_04_map_hover.png
│   ├── screenshot_05_map_popup_tp.png
│   ├── screenshot_06_map_popup_fp.png
│   ├── screenshot_07_station_plot_anomaly.png
│   ├── screenshot_08_station_plot_normal.png
│   ├── screenshot_09_chart_7day.png
│   ├── screenshot_10_chart_status.png
│   ├── screenshot_11_chart_success.png
│   ├── screenshot_12_chart_magnitude.png
│   ├── screenshot_13_data_availability.png
│   └── screenshot_14_mobile.png (optional)
```

---

## 🛠️ Tools for Screenshots

### Windows Built-in:
- **Snipping Tool**: Windows + Shift + S
- **Game Bar**: Windows + G (for full-screen capture)

### Browser Extensions:
- **Chrome**: Full Page Screen Capture
- **Firefox**: Firefox Screenshots (built-in)

### Third-party Tools:
- **ShareX** (free, powerful)
- **Greenshot** (free, easy to use)
- **Lightshot** (free, simple)

---

## ✅ Quality Checklist

Before submitting, verify each screenshot:
- [ ] High resolution (at least 1920x1080 for desktop views)
- [ ] All text is readable
- [ ] No personal information visible (browser bookmarks, etc.)
- [ ] Correct filename
- [ ] PNG format
- [ ] All UI elements fully loaded
- [ ] No loading spinners or incomplete renders

---

## 📝 Screenshot Descriptions

After capturing, create a document listing each screenshot with descriptions:

**Example**:
```
Screenshot 1: Main dashboard in light mode showing summary statistics (51 active stations, 
0 anomalies detected), data availability report (100% coverage), four analytical charts 
(7-day trend, station status, detection success rate, magnitude distribution), and 
interactive global map with 51 station markers.

Screenshot 2: Same dashboard view in dark mode, demonstrating responsive theme switching 
and improved readability in low-light conditions.

[Continue for all screenshots...]
```

---

## 🎯 Priority Screenshots

If time is limited, capture these **minimum required** screenshots:
1. ✅ Dashboard Light Mode (Screenshot 1)
2. ✅ Dashboard Dark Mode (Screenshot 2)
3. ✅ Map with TP Popup (Screenshot 5)
4. ✅ Station Plot with Anomaly (Screenshot 7)
5. ✅ All 4 Charts (Screenshots 9-12)

---

**Last Updated**: February 5, 2026  
**Created by**: Nur Syaiful Afrizal
