# GEMPRA — Copyright Application Slide Content

> Copy each section into the corresponding slide of the UPM template.

---

## SLIDE 1 — DETAILS OF WORKS

### Overview of the Work

**GEMPRA** (Geomagnetic Earthquake Monitoring Platform using Polarization Ratio Analysis) is a **web-based scientific monitoring system** developed as an original software work. It is deployed as a fully functional, publicly accessible web application at [https://syaifulafrizal.github.io/global-pra-observation](https://syaifulafrizal.github.io/global-pra-observation).

The system continuously monitors geomagnetic field data from **51+ global observatories** (INTERMAGNET network) and applies a novel two-stage anomaly detection pipeline — **Multitaper Spectral Analysis (MTM)** combined with **Extreme Value Theory (EVT)** — to identify potential electromagnetic precursors to earthquakes. Detected anomalies are automatically correlated with earthquake events sourced from the USGS seismic catalogue. Results are rendered in an **interactive real-time dashboard** featuring global maps, analytical charts, and per-station diagnostic plots.

**Form**: Web application software (HTML5/CSS3/JavaScript + Python backend processing)
**Intended Use**: Academic research, earthquake precursor monitoring, geophysics education, public science awareness

---

### Originality of the Work

**Skill** — The system integrates advanced digital signal processing (Multitaper Spectral Method with DPSS tapers, NW=3.5), statistical extreme value analysis (GEV distribution fitting via SciPy), geospatial correlation (Haversine-based radius search), and modern interactive web development — combining disciplines that span geophysics, data science, and full-stack software engineering.

**Judgement** — The author independently selected and adapted the MTM+EVT framework (originally used in seismology) to geomagnetic anomaly detection in the ULF frequency band (0.095–0.110 Hz), chose the 14-day temporal correlation window based on published earthquake precursor research, and designed a hybrid data aggregation strategy that reduced frontend network requests by 98% (from 350+ to 7 per page load).

**Effort** — The platform was developed through iterative design and testing cycles: acquisition pipeline (INTERMAGNET data parsing → preprocessing → spectral computation), anomaly classification logic (TP/FP/FN), earthquake correlation engine, data aggregation system (`upload_results.py`, `integrate_earthquakes.py`), and full frontend implementation with dark/light mode, responsive map, and Chart.js visualisations. Automated daily execution via Windows Task Scheduler (GMT+8) and deployment to GitHub Pages were independently engineered.

---

### Use of Existing Platforms / Background IP (if any)

The following open-source third-party tools and public APIs are used as background infrastructure. The copyrighted original work lies entirely in the **system architecture design, analytical methodology, processing logic, and web implementation**:

| Component | Role | Original Work Boundary |
|---|---|---|
| **Python 3.x** (NumPy, SciPy, Pandas, Geopy) | Computation environment | All algorithms and processing scripts are original |
| **INTERMAGNET Network** | Public geomagnetic data source | Data acquisition module and parsing logic are original |
| **USGS FDSN Earthquake API** | Public earthquake catalogue | Correlation engine and classification logic are original |
| **Leaflet.js** | Map rendering library | All map configuration, marker logic, popup content, 200km circle hover are original |
| **Chart.js** | Chart rendering library | All chart types, data structures, and rendering logic are original |
| **GitHub Pages** | Static web hosting | Site structure, deployment pipeline, and automation scripts are original |

No proprietary software (e.g. MATLAB, Unity) was used. All source code was written by the author from scratch.

---

## SLIDE 2 — ADDITIONAL DESCRIPTION

### Work Process / System Flow

GEMPRA operates through an **8-stage automated pipeline** (refer to attached system pipeline diagram):

1. **INTERMAGNET Data Retrieval** — Daily download of geomagnetic .min files (IAGA-2002 format) for 51 stations; time window 20:00–04:00 local time
2. **Preprocessing** — Parsing, missing value interpolation, outlier removal (3σ clipping), unit normalisation to nT
3. **Spectral Analysis (MTM)** — Multitaper Power Spectral Density estimation (K=6 DPSS tapers, NW=3.5); frequency band 0.095–0.110 Hz; PR = √(H²+D²) / Z computed per station
4. **Anomaly Detection (EVT)** — 30-day baseline GEV distribution fitted via SciPy; threshold = 95th percentile; stations flagged `is_anomalous` if PR exceeds threshold for ≥1 hour
5. **Earthquake Integration** — USGS API queried for M≥5.0 events within 200 km radius and 14-day window; classified as TP, FP, or FN
6. **Data Aggregation** — Per-station JSON files combined into single `aggregated_{date}.json`; persistent anomaly history and false negative logs maintained
7. **Web Output Preparation** — Static files assembled in `web_output/`; PRA plots (PNG), CSVs, stations.json metadata prepared
8. **Automated Deployment** — Windows Task Scheduler (GMT+8) triggers PowerShell script daily; git commit + push to GitHub Pages serves live dashboard

---

### Final Output / Deliverables

- ✅ **Live web application**: [https://syaifulafrizal.github.io/global-pra-observation](https://syaifulafrizal.github.io/global-pra-observation)
- ✅ **Interactive global station map** with colour-coded anomaly status (Gray = Normal, Orange = True Positive, Red = False Positive)
- ✅ **4 analytical charts**: 7-Day Anomaly Trend, Station Status Distribution, Detection Success Rate, Magnitude Distribution
- ✅ **Per-station PRA diagnostic plots** with EVT threshold line overlaid
- ✅ **Downloadable anomaly CSV** for research use
- ✅ **Fully automated daily processing pipeline** (Python scripts + PowerShell automation)
- ✅ **Source code**: Complete Python backend + HTML/CSS/JS frontend

---

### Demonstration & Verification

The system is **live and functional** at the published URL. It can be demonstrated in real-time during the evaluation session to verify:
- Live data loading from GitHub Pages CDN
- Date selection and dynamic dashboard update
- Interactive map with station popups, 200km radius hover circles
- Per-station PRA plot rendering
- Dark/Light mode toggle
- CSV download functionality

The automated processing pipeline has been running successfully in production since deployment.

---

### Prototype / Supporting Materials

Available for review:
- System pipeline diagram (attached)
- Source code listings (Python backend, JavaScript frontend)
- Screenshots of all major dashboard views (light mode, dark mode, map popups, charts, station plots)
- Copyright attachments package: System Architecture, PRA Methodology, Technical Specifications, User Guide, Source Code Samples, Deployment Automation documentation

---

### System Executability

All source code is **fully executable and functional**. The system runs on Python 3.8+ (Windows/Linux) and serves via any modern web browser. The live deployment is accessible globally without login. Automated batch processing runs daily without manual intervention.

---

## SLIDE 3 — WORK COMPARISON / COMPETITOR(S)

### Use of Public or Common Sources

☑ **The work contains materials derived from public documents or common sources**

- Geomagnetic data sourced from INTERMAGNET (public, open-access observatory network)
- Earthquake data sourced from USGS FDSN API (public federal database)
- The **original copyrighted work** lies entirely in the analytical methodology (MTM+EVT pipeline), system architecture, processing scripts, and interactive web implementation — none of which are derived from existing platforms or publications

---

### Closest Comparable Works / Existing Solutions

| | **GEMPRA (This Work)** | **Comparison 1: SuperMAG / INTERMAGNET Web Portal** | **Comparison 2: RSOE EDIS / Earthquake Alert Systems** |
|---|---|---|---|
| **Works** | Web platform applying MTM+EVT PRA for earthquake precursor detection from geomagnetic ULF data | Web portals providing raw geomagnetic data and basic visualisations | Web-based real-time earthquake alert and notification systems |
| **Similarity** | Uses geomagnetic data from the global network, provides web-based access | Uses same geomagnetic data source (INTERMAGNET); web-based | Monitors seismic activity; web dashboard with global map |
| **Difference** | ✅ Applies novel MTM spectral analysis + EVT anomaly detection in the 0.095–0.110 Hz ULF band specifically for earthquake precursor identification; automatically correlates anomalies with USGS earthquake events; classifies detections as TP/FP/FN; fully automated daily pipeline; interactive per-station diagnostic plots | ❌ No anomaly detection; no earthquake correlation; no PRA methodology; raw data portal only, no predictive analysis | ❌ Detects earthquakes **after** they occur (seismometer-based); does not detect pre-earthquake geomagnetic anomalies; no PRA or ULF analysis; no TP/FP/FN classification |

**Key Differentiators of GEMPRA:**
- Only publicly accessible platform implementing **MTM + EVT** for geomagnetic earthquake precursor monitoring at global scale
- Automated **TP/FP/FN classification** with persistent historical logging — not available in any comparable tool
- **98% reduction in data requests** through hybrid aggregation — original engineering contribution
- End-to-end pipeline from raw .min file download to live interactive web dashboard — fully self-contained and automated

---

## SLIDE 4 — DEFINE THE WORK & POTENTIAL (Part 1)

### 1. The Work Is:
**A fully operational, original web-based scientific monitoring software** implementing a novel geomagnetic anomaly detection methodology (MTM + EVT) for earthquake precursor identification, with automated daily data processing, real-time interactive visualisation, and global station coverage.

- **Commercial applications:**
  - Licensing to national meteorological and geophysical agencies (e.g. MetMalaysia, BMKG Indonesia, JMA Japan) for integration into early warning research infrastructure
  - Academic SaaS platform for university geophysics departments conducting LAIC (Lithosphere-Atmosphere-Ionosphere Coupling) research
  - Government disaster risk reduction agencies seeking cost-effective geomagnetic monitoring tools

- **Perceived advantages & benefits:**
  - **Low cost**: Leverages entirely free public data sources (INTERMAGNET, USGS) — no proprietary data licences required
  - **Global coverage**: 51+ stations spanning Asia, Americas, Europe, Africa, and Oceania
  - **Scientific rigour**: MTM + EVT methodology grounded in peer-reviewed geophysics literature
  - **Accessibility**: Zero-installation, browser-based dashboard accessible to researchers and public worldwide
  - **Automation**: Fully hands-off daily processing pipeline — no manual intervention required

- **Value proposition:**
  GEMPRA provides the **only freely accessible, automated, global-scale geomagnetic earthquake precursor monitoring platform** that applies the MTM+EVT pipeline with real-time TP/FP/FN earthquake correlation — delivering research-grade analysis at zero operational cost to end users.

- **Limitation of the work / constraints:**
  - Geomagnetic precursors are probabilistic indicators, not deterministic predictions — system supports research, not operational earthquake forecasting
  - Dependent on INTERMAGNET station data availability (~85–100% coverage daily)
  - 14-day correlation window means final TP/FP classification requires retrospective confirmation

- **Turnitin score**: To be provided with submission (target < 25%)

### 2. Market:
- **Primary**: Academic and research institutions in geophysics, seismology, and disaster risk management — globally, with focus on Southeast Asia (Malaysia, Indonesia, Philippines) where seismic risk is high
- **Secondary**: National disaster management agencies (NADMA Malaysia, BNPB Indonesia) and observatory networks seeking supplementary monitoring tools
- **Tertiary**: Science educators and the general public interested in real-time global geophysical monitoring

---

## SLIDE 5 — DEFINE THE WORK & POTENTIAL (Part 2)

### 4. Commercial Readiness

- **Current Status**: **Prototype — Fully Functional & Publicly Deployed**
  The platform is live and operational at [https://syaifulafrizal.github.io/global-pra-observation](https://syaifulafrizal.github.io/global-pra-observation). It processes daily data automatically and serves a real-time dashboard without any manual intervention. The system is ready for pilot user evaluation by research institutions.

- **Commercial Model**:
  - **Licensing**: The MTM+EVT processing pipeline and web platform can be licensed to government agencies or research consortia for integration into national geophysical monitoring infrastructure
  - **Service-based**: The automated processing pipeline can be offered as a subscription-based monitoring service — delivering daily geomagnetic anomaly reports and earthquake correlation analytics to subscribing organisations
  - **Spin-off**: Potential to develop into a standalone commercial early warning research tool with enhanced features (push notifications, API access, multi-parameter anomaly integration with ionospheric and atmospheric data)

- **Industry Interest & Engagement**:
  - Developed under research framework at **Universiti Putra Malaysia (UPM)** with academic supervision
  - Aligned with **UNDRR Sendai Framework** goals for disaster risk reduction through science-based monitoring
  - Potential engagement with **ASEAN Earthquake Information Centre** and regional meteorological agencies
  - Methodology is publication-ready for submission to international geophysics journals (Journal of Geophysical Research, Natural Hazards and Earth System Sciences)
