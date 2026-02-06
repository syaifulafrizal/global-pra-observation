# Copyright Application for GEMPRA Platform

## PART B: RESEARCH INFORMATION

### Title of Inventions
**GEMPRA - Geomagnetic Earthquake Monitoring Platform using Polarization Ratio Analysis**

### Title of Research Project
**Real-time Earthquake Precursor Detection using Geomagnetic Field Analysis and Polarization Ratio Analysis (PRA)**

### Research Project PTJ7
*[To be filled based on your university's project tracking number]*

### Department
**Department of Physics / Institute of Advanced Technology (ITMA)**
**Universiti Putra Malaysia (UPM)**

### Source of Fund

| # | Vot Number | Grant Type | Grant Title | Sponsor |
|---|------------|------------|-------------|---------|
| 1 | 5540629 | FRGS | Pre-earthquake Anomaly Sequence Identification in Accordance with the Coupling Mechanism of Earth Layers Based on Multiparametric Observations | Ministry of Higher Education Malaysia |
| 2 | 9710900 | GP-IPM | Feature Reduction of Geomagnetic Data for Machine Learning-Based Earthquake Precursor Detector | Universiti Putra Malaysia |

### Vot Number
**5540629 / 9710900** (Select primary funding source)

### Research Cluster
*[To be filled based on UPM's research cluster classification - likely "Natural Disaster & Climate Change" or "Advanced Technology & Engineering"]*

---

## PART C: OWNERSHIP

### a) Institution:

| # | Owner & Co-Owner | Distribution (%) |
|---|------------------|------------------|
| 1 | Universiti Putra Malaysia (UPM) | 100% |

**Total: 100%**

*Based on agreement: Research conducted under UPM funding and facilities*

---

### b) Inventors (Staff):

| # | Inventor/Researcher(s) | PTJ/Faculty | Passport/IC No.33 | Nationality | Contribution Percentage (%) |
|---|------------------------|-------------|-------------------|-------------|----------------------------|
| 1 | Nur Syaiful Afrizal | Institute of Advanced Technology (ITMA) / Faculty of Science | *[Your IC/Passport]* | Malaysian | 70% |
| 2 | *[Supervisor Name]* | *[Department]* | *[IC/Passport]* | Malaysian | 20% |
| 3 | *[Co-supervisor/Collaborator if any]* | *[Department]* | *[IC/Passport]* | Malaysian | 10% |

**Total: 100%**

*Should include project leader's name and all contributing researchers*

---

### b) Inventors (Non Staff):
*[Leave blank if all inventors are UPM staff]*

---

## PART D: INVENTION OF WORK

### 1) Has the work been disclosed in any way?
**NO** *(Select YES if you have published papers, presented at conferences, or publicly deployed the website)*

*If YES, provide details:*
- Conference presentations
- Journal publications
- Public website deployment (https://syaifulafrizal.github.io/global-pra-observation/)
- GitHub repository (if public)

---

### 2) Starting date of the works:
**01-01-2024** *(Adjust based on when you actually started development)*

---

### 3) Completion date of the work:
**05-01-2026** *(Current date or expected completion)*

---

### 4) Nominee:
**Nur Syaiful Afrizal**

---

### 5) Description of creative works

**Classification:** Computer Software / Web Application

**Title:** GEMPRA - Geomagnetic Earthquake Monitoring Platform using Polarization Ratio Analysis

**Description:**

GEMPRA is a comprehensive full-stack web-based platform for real-time earthquake precursor detection through geomagnetic field analysis. The system processes data from 51+ global magnetometer stations (INTERMAGNET network) and correlates geomagnetic anomalies with earthquake events from USGS database.

**Technical Components:**

1. **Backend Processing System (Python)**
   - Automated data acquisition from INTERMAGNET stations
   - Multitaper Spectral Analysis (NW=3.5) for frequency domain analysis
   - Extreme Value Theory (EVT) for anomaly threshold determination
   - Polarization Ratio Analysis (PRA) methodology implementation
   - USGS Earthquake API integration for real-time correlation
   - Geospatial distance calculations (200km radius monitoring)
   - Statistical analysis engine (True Positive/False Positive/False Negative tracking)

2. **Frontend Visualization System (JavaScript/HTML/CSS)**
   - Interactive global station map using Leaflet.js
   - Real-time data visualization with Chart.js
   - Date-based data navigation (7-day rolling window)
   - Responsive dashboard with dark/light mode
   - Station-specific analysis plots
   - Earthquake correlation display with magnitude filtering

3. **Data Architecture**
   - Hybrid data aggregation system (98% reduction in network requests)
   - Persistent historical anomaly tracking
   - Date-specific file management with automatic cleanup
   - Fallback data logic for continuous availability
   - JSON-based data interchange format

4. **Deployment Infrastructure**
   - Automated daily processing via Windows Task Scheduler (GMT+8)
   - Static site deployment on GitHub Pages
   - PowerShell automation scripts for batch processing
   - Local Windows environment with scheduled execution

**Novel Features:**
- Polarization Ratio Analysis (PRA) methodology for earthquake precursor detection
- Automated correlation between geomagnetic anomalies and M≥5.0 earthquakes
- Real-time false negative detection (missed earthquake events)
- Multi-station global monitoring network
- Time window analysis (20:00-04:00 local time, 0.095-0.110 Hz frequency band)

**Research Contribution:**
This platform enables systematic validation of the PRA methodology for earthquake precursor detection, providing researchers with tools to analyze geomagnetic-seismic correlations across multiple geographic locations and time periods.

**Attachments:**
- Source code repository structure
- System architecture diagrams
- Sample dashboard screenshots
- Data flow diagrams
- Algorithm flowcharts

---

### 6) Has the creativity work been protected for other type of protection?
**NO**

*If YES, specify type (Patent, Trademark, Industrial Design, etc.)*

---

### 7) Stage of creativity work development:

**Completed and Operational**

The platform is fully developed, tested, and deployed with:
- Live production deployment at: https://syaifulafrizal.github.io/global-pra-observation/
- Processing data from 51+ active stations
- Daily automated updates
- Historical data spanning multiple months
- Proven correlation analysis capabilities

---

## SUPPORTING DOCUMENTATION CHECKLIST

**Required Attachments:**

1. ✅ **Source Code**
   - Complete codebase (Python backend + JavaScript frontend)
   - Configuration files
   - Deployment scripts

2. ✅ **Technical Documentation**
   - System architecture diagram
   - Data flow diagrams
   - Algorithm descriptions
   - API documentation

3. ✅ **Screenshots/Visual Evidence**
   - Dashboard interface (light/dark modes)
   - Interactive map with station markers
   - Chart visualizations
   - Station analysis plots
   - Data availability reports

4. ✅ **Research Documentation**
   - PRA methodology description
   - Statistical analysis methods
   - Validation results
   - Sample output data

5. ✅ **Deployment Evidence**
   - Live website URL
   - GitHub repository (if applicable)
   - Deployment logs

6. ⚠️ **Funding Acknowledgment**
   - Grant agreement documents
   - Budget allocation proof
   - University approval letters

---

## DECLARATION

**I do solemnly and sincerely declare that all information given is true and original work.**

**Name:** Nur Syaiful Afrizal  
**Date:** 04-02-2026  
**Signature:** ___________________

---

## NOTES FOR COMPLETION

1. **Verify all personal information** (IC/Passport numbers, exact names)
2. **Confirm funding sources** with your supervisor/research office
3. **Get supervisor approval** before submission
4. **Prepare all attachments** in required formats (PDF for documents, PNG/JPG for images)
5. **Check university IP policy** regarding ownership percentages
6. **Consult with UPM Innovation & Commercialization Centre** for guidance
7. **Keep copies** of all submitted materials

---

## ADDITIONAL INFORMATION

### Keywords for Classification:
- Earthquake Precursor Detection
- Geomagnetic Field Analysis
- Polarization Ratio Analysis (PRA)
- Real-time Monitoring System
- Web-based Scientific Platform
- Data Visualization
- Seismic-Electromagnetic Correlation
- INTERMAGNET Network
- USGS Integration

### Technology Stack:
- **Backend:** Python 3.x, NumPy, Pandas, SciPy, Geopy
- **Frontend:** JavaScript (ES6+), HTML5, CSS3, Leaflet.js, Chart.js
- **Data Sources:** INTERMAGNET, USGS Earthquake API
- **Deployment:** GitHub Pages, GitHub Actions
- **Version Control:** Git

### Potential Applications:
1. Academic research in earthquake precursor studies
2. Geomagnetic observatory data analysis
3. Multi-station correlation studies
4. Educational tool for geophysics students
5. Early warning system development research
6. Natural disaster preparedness research

---

**Contact Information:**
- **Developer:** Nur Syaiful Afrizal
- **Institution:** Universiti Putra Malaysia
- **Email:** *[Your UPM email]*
- **GitHub:** https://github.com/syaifulafrizal
- **Project URL:** https://syaifulafrizal.github.io/global-pra-observation/
