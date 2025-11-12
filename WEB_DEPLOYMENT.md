# Web App Deployment Guide

## Current Architecture

The system is **already a web application** using Flask, but with a specific architecture:

```
┌─────────────────┐
│  Server PC      │
│                 │
│  1. Processing  │ ← pra_nighttime.py (runs on server)
│  2. Web Server  │ ← app.py (Flask, serves dashboard)
│  3. Data Store  │ ← INTERMAGNET_DOWNLOADS/
└─────────────────┘
         │
         └──> Browser (http://localhost:5000)
```

## Deployment Options

### Option 1: Current Setup (Recommended)
**Local Server with Web Interface**

- ✅ Processing runs on your server PC
- ✅ Web dashboard for viewing results
- ✅ No external dependencies
- ✅ Full control over data

**Best for**: Personal/research use, single server deployment

---

### Option 2: Cloud Web Service
**Deploy Flask app to cloud hosting**

#### Platforms:
- **Heroku**: Easy deployment, but processing time limits
- **Railway**: Good for background jobs
- **DigitalOcean App Platform**: Full control
- **AWS/GCP/Azure**: Enterprise-grade

#### Requirements:
1. Move processing to background tasks (Celery/Redis)
2. Use cloud storage (S3, etc.) for data
3. Set up scheduled jobs (cron/APScheduler)
4. Environment variables for configuration

**Best for**: Public access, multiple users

---

### Option 3: Serverless Functions
**Split into microservices**

- Processing: AWS Lambda / Google Cloud Functions
- API: Flask API on serverless
- Frontend: Static hosting (Vercel, Netlify)
- Storage: Cloud database (PostgreSQL, MongoDB)

**Best for**: Scalable, pay-per-use model

---

### Option 4: Full Web App (Browser-based)
**Client-side processing** (NOT recommended)

❌ **Not feasible** because:
- Large data downloads (1-second resolution)
- CPU-intensive processing (Multitaper, EVT)
- Browser memory limits
- Security restrictions (CORS, file access)

---

## Recommended: Hybrid Approach

Keep current architecture but add:

### A. API Endpoints
Add REST API to Flask for programmatic access:

```python
@app.route('/api/analyze/<station>', methods=['POST'])
def trigger_analysis(station):
    # Trigger analysis for specific station
    # Return job ID
    pass

@app.route('/api/status/<job_id>')
def get_status(job_id):
    # Return processing status
    pass
```

### B. Background Processing
Use Celery for async processing:

```python
from celery import Celery

celery = Celery('pra_analysis')

@celery.task
def process_station_async(station_code):
    # Run pra_nighttime.py for station
    pass
```

### C. Scheduled Jobs
Use APScheduler for daily runs:

```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.add_job(
    func=run_daily_analysis,
    trigger="cron",
    hour=8,
    minute=0,
    timezone="Asia/Singapore"
)
```

---

## Quick Cloud Deployment (Railway/Heroku)

### Step 1: Add Procfile
```
web: gunicorn app:app
worker: python pra_nighttime.py
```

### Step 2: Add requirements
```
gunicorn>=20.1.0
apscheduler>=3.10.0
```

### Step 3: Environment Variables
```
INTERMAGNET_STATIONS=
TZ=Asia/Singapore
```

### Step 4: Deploy
```bash
git push railway main
```

---

## Current System: Web-Ready ✅

Your current setup **IS a web application**:
- ✅ Flask web server
- ✅ RESTful API endpoints
- ✅ Interactive frontend
- ✅ Real-time data serving

**What makes it "web app ready":**
1. Flask serves HTML/CSS/JS
2. API endpoints for data (`/api/stations`, `/data/`)
3. Static file serving
4. Can be deployed to any WSGI-compatible host

**To make it "cloud-ready":**
1. Add background task queue (Celery)
2. Use cloud storage for data
3. Add authentication (if needed)
4. Set up scheduled jobs

---

## Summary

| Aspect | Current | Cloud-Ready | Full Web App |
|--------|--------|-------------|--------------|
| Processing | Server PC | Cloud server | ❌ Not feasible |
| Web Interface | ✅ Flask | ✅ Flask/API | ✅ React/Vue |
| Data Storage | Local files | Cloud storage | Cloud DB |
| Scheduling | Manual/cron | Cloud scheduler | Cloud scheduler |
| Access | Local network | Public URL | Public URL |

**Your system is already a web app** - it just needs deployment configuration for cloud hosting.

