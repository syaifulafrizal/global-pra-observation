// Enhanced frontend JavaScript for PRA Dashboard with Map - Earthquake Theme

const DATA_URL = 'data/stations.json';

let allStationsData = {};
let stationMetadata = {};
let map = null;
let markers = {};
let allStations = [];
let anomalousStations = [];

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    renderDashboard();
    setInterval(renderDashboard, 300000); // Auto-refresh every 5 minutes
});

async function loadData() {
    try {
        const response = await fetch(DATA_URL);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error loading data:', error);
        return null;
    }
}

async function loadEarthquakeCorrelations(station) {
    try {
        const response = await fetch(`data/${station}_earthquake_correlations.csv`);
        if (!response.ok) {
            return [];
        }
        const text = await response.text();
        const correlations = parseCSV(text);
        // Filter by magnitude >= 5.5 for reliability
        return correlations.filter(eq => parseFloat(eq.earthquake_magnitude || 0) >= 5.5);
    } catch (error) {
        return [];
    }
}

async function loadFalseNegatives(station) {
    try {
        const response = await fetch(`data/${station}_false_negatives.csv`);
        if (!response.ok) {
            return [];
        }
        const text = await response.text();
        return parseCSV(text);
    } catch (error) {
        return [];
    }
}

async function loadRecentEarthquakes() {
    try {
        const response = await fetch('data/recent_earthquakes.csv');
        if (!response.ok) {
            return [];
        }
        const text = await response.text();
        return parseCSV(text);
    } catch (error) {
        return [];
    }
}

function parseCSV(csvText) {
    const lines = csvText.split('\n').filter(line => line.trim());
    if (lines.length < 2) return [];
    
    const headers = lines[0].split(',').map(h => h.trim());
    const data = [];
    
    for (let i = 1; i < lines.length; i++) {
        const values = lines[i].split(',').map(v => v.trim());
        const row = {};
        headers.forEach((header, idx) => {
            row[header] = values[idx] || '';
        });
        data.push(row);
    }
    
    return data;
}

function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

function initMap() {
    const mapContainer = document.getElementById('map-container');
    if (!mapContainer) {
        console.error('Map container not found');
        return;
    }
    
    if (map) {
        try {
            map.remove();
        } catch (e) {}
    }
    
    try {
        map = L.map('map-container', {
            minZoom: 2,  // Prevent zooming out too far
            maxZoom: 10, // Limit maximum zoom
            zoomControl: true
        }).setView([20, 0], 2);
        
        // Set max bounds to prevent panning too far
        const southWest = L.latLng(-85, -180);
        const northEast = L.latLng(85, 180);
        const bounds = L.latLngBounds(southWest, northEast);
        map.setMaxBounds(bounds);
        
        // Add OpenStreetMap tiles with earthquake-themed styling
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            minZoom: 2,
            maxZoom: 10
        }).addTo(map);
        
        // Clear existing markers
        Object.values(markers).forEach(marker => {
            try {
                marker.remove();
            } catch (e) {}
        });
        markers = {};
    } catch (error) {
        console.error('Error creating map:', error);
    }
}

function addStationToMap(stationCode, stationData, eqCorrelations) {
    if (!map) {
        console.warn('Map not initialized, skipping marker for', stationCode);
        return;
    }
    
    const metadata = stationMetadata[stationCode];
    if (!metadata || !metadata.latitude || !metadata.longitude) {
        console.warn(`Missing metadata for ${stationCode}`);
        return;
    }
    
    const hasAnomaly = stationData && stationData.is_anomalous;
    const hasEQ = eqCorrelations && eqCorrelations.length > 0;
    
    // Earthquake-themed colors
    let color = 'gray'; // No anomaly
    if (hasAnomaly) {
        color = hasEQ ? 'eq-reliable' : 'eq-false'; // Orange if EQ found, red if false alarm
    }
    
    // Create custom icon with earthquake theme
    const icon = L.divIcon({
        className: 'station-marker',
        html: `<div class="marker-dot marker-${color}"></div>`,
        iconSize: [24, 24],
        iconAnchor: [12, 12]
    });
    
    // Create popup content with earthquake info
    let popupContent = `<div style="min-width: 220px; font-family: Arial, sans-serif;"><strong style="color: #c0392b; font-size: 1.1em;">${metadata.name || stationCode} (${stationCode})</strong><br>`;
    popupContent += `<span style="color: #7f8c8d;">${metadata.country || 'Unknown'}</span><br>`;
    popupContent += `<small>📍 ${metadata.latitude ? metadata.latitude.toFixed(3) : 'N/A'}, ${metadata.longitude ? metadata.longitude.toFixed(3) : 'N/A'}</small><br>`;
    
    if (hasAnomaly && stationData) {
        popupContent += `<hr style="margin: 8px 0; border-color: #e74c3c;"><strong style="color: #e74c3c;">⚠️ Anomaly Detected</strong><br>`;
        popupContent += `📅 ${formatDate(stationData.date)}<br>`;
        popupContent += `📊 Threshold: ${parseFloat(stationData.threshold || 0).toFixed(2)}<br>`;
        popupContent += `⏱️ Anomaly Hours: ${stationData.nAnomHours || 0}<br>`;
        
        // Filter by magnitude >= 5.5 for display
        const reliableCorrelations = eqCorrelations.filter(eq => parseFloat(eq.earthquake_magnitude || 0) >= 5.5);
        if (hasEQ && reliableCorrelations.length > 0) {
            popupContent += `<hr style="margin: 8px 0; border-color: #e67e22;"><strong style="color: #e67e22;">🌋 EQ Correlation Found (M≥5.5): ${reliableCorrelations.length}</strong><br>`;
            reliableCorrelations.slice(0, 3).forEach((eq) => {
                const mag = eq.earthquake_magnitude || 'N/A';
                const dist = parseFloat(eq.earthquake_distance_km || 0).toFixed(1);
                const days = parseFloat(eq.days_before_anomaly || 0).toFixed(1);
                popupContent += `🔴 M${mag} @ ${dist}km (${days} days before)<br>`;
            });
            if (reliableCorrelations.length > 3) {
                popupContent += `... and ${reliableCorrelations.length - 3} more<br>`;
            }
        } else {
            popupContent += `<hr style="margin: 8px 0; border-color: #e74c3c;"><strong style="color: #e74c3c;">⚠️ False Alarm</strong><br>`;
            popupContent += `No EQ M≥5.5 within 200km within 14 days`;
        }
    } else {
        popupContent += `<hr style="margin: 8px 0; border-color: #95a5a6;"><span style="color: #95a5a6;">✅ Status: Normal</span><br>`;
        popupContent += `No anomalies detected`;
    }
    popupContent += `</div>`;
    
    // Add marker to map
    const marker = L.marker([metadata.latitude, metadata.longitude], { icon })
        .addTo(map)
        .bindPopup(popupContent);
    
    markers[stationCode] = marker;
}

function addEarthquakeMarkers(earthquakes) {
    if (!map) {
        console.warn('Map not initialized, cannot add earthquake markers');
        return;
    }
    
    if (!earthquakes || earthquakes.length === 0) {
        console.log('No earthquakes to display on map');
        return;
    }
    
    console.log(`Adding ${earthquakes.length} earthquake markers to map`);
    
    earthquakes.forEach((eq, index) => {
        const lat = parseFloat(eq.latitude || eq.earthquake_latitude);
        const lon = parseFloat(eq.longitude || eq.earthquake_longitude);
        const mag = parseFloat(eq.magnitude || eq.earthquake_magnitude || 0);
        const place = eq.place || eq.earthquake_place || 'Unknown';
        const time = eq.time || eq.earthquake_time || '';
        
        console.log(`EQ ${index + 1}: lat=${lat}, lon=${lon}, mag=${mag}, place=${place}`);
        
        if (isNaN(lat) || isNaN(lon)) {
            console.warn(`Skipping earthquake ${index + 1}: invalid coordinates (lat=${lat}, lon=${lon})`);
            return;
        }
        
        // Create earthquake icon (red triangle)
        const icon = L.divIcon({
            className: 'earthquake-marker',
            html: `<div class="eq-marker" style="
                width: ${Math.max(20, Math.min(40, mag * 5))}px;
                height: ${Math.max(20, Math.min(40, mag * 5))}px;
                background: #e74c3c;
                border: 2px solid white;
                border-radius: 50%;
                box-shadow: 0 2px 8px rgba(0,0,0,0.4);
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: bold;
                font-size: ${Math.max(10, Math.min(14, mag * 2))}px;
            ">${mag.toFixed(1)}</div>`,
            iconSize: [Math.max(20, Math.min(40, mag * 5)), Math.max(20, Math.min(40, mag * 5))],
            iconAnchor: [Math.max(10, Math.min(20, mag * 2.5)), Math.max(10, Math.min(20, mag * 2.5))]
        });
        
        // Create popup
        const dateStr = time ? new Date(time).toLocaleString() : 'Unknown';
        const popupContent = `
            <div style="min-width: 200px; font-family: Arial, sans-serif;">
                <strong style="color: #e74c3c; font-size: 1.2em;">🌋 Earthquake M${mag.toFixed(1)}</strong><br>
                <span style="color: #555;">${place}</span><br>
                <small>📅 ${dateStr}</small><br>
                <small>📍 ${lat.toFixed(3)}, ${lon.toFixed(3)}</small>
            </div>
        `;
        
        // Add marker
        const marker = L.marker([lat, lon], { icon })
            .addTo(map)
            .bindPopup(popupContent);
        
        console.log(`Added earthquake marker at [${lat}, ${lon}] with magnitude ${mag}`);
        
        // Store in a separate object for earthquakes
        if (!markers.earthquakes) {
            markers.earthquakes = [];
        }
        markers.earthquakes.push(marker);
    });
    
    console.log(`Total earthquake markers added: ${markers.earthquakes ? markers.earthquakes.length : 0}`);
}

async function renderDashboard() {
    const container = document.getElementById('stations-container');
    if (!container) return;
    
    container.innerHTML = '<p style="text-align: center; color: white; font-size: 1.2em;">Loading data...</p>';
    
    const data = await loadData();
    if (!data) {
        container.innerHTML = '<p class="no-data">❌ Failed to load data. Make sure to run upload_results.py first.</p>';
        return;
    }
    
    // Load metadata
    if (data.metadata && Array.isArray(data.metadata)) {
        data.metadata.forEach(station => {
            stationMetadata[station.code] = station;
        });
    }
    
    allStations = data.stations || [];
    allStationsData = data.data || {};
    
    // Identify anomalous stations
    anomalousStations = [];
    let totalStations = 0;
    let anomalousCount = 0;
    let withEQ = 0;
    let falseAlarms = 0;
    let falseNegatives = 0;
    
    const stationDataMap = {};
    for (const station of allStations) {
        totalStations++;
        const stationData = allStationsData[station];
        const hasAnomaly = stationData && stationData.is_anomalous;
        
        if (hasAnomaly) {
            anomalousCount++;
            anomalousStations.push(station);
            const eqCorrelations = await loadEarthquakeCorrelations(station);
            // Filter by magnitude >= 5.5 for reliability
            const reliableCorrelations = eqCorrelations.filter(eq => parseFloat(eq.earthquake_magnitude || 0) >= 5.5);
            if (reliableCorrelations.length > 0) {
                withEQ++;
            } else {
                falseAlarms++;
            }
            stationDataMap[station] = { stationData, eqCorrelations: reliableCorrelations };
        } else {
            // Check for false negatives (EQ >= 5.5 occurred but no anomaly)
            const fn = await loadFalseNegatives(station);
            falseNegatives += fn.length;
            stationDataMap[station] = { stationData: null, eqCorrelations: [], falseNegatives: fn };
        }
    }
    
    let html = '';
    
    // Load today's earthquake statistics
    let todayEQStats = { global: 0, within200km: 0 };
    try {
        const statsResponse = await fetch('data/today_earthquake_stats.json');
        if (statsResponse.ok) {
            const statsData = await statsResponse.json();
            // Map JSON keys to JavaScript property names
            todayEQStats = {
                global: statsData.global_count || statsData.global || 0,
                within200km: statsData.within_200km_count || statsData.within200km || 0
            };
        }
    } catch (error) {
        console.warn('Could not load earthquake statistics:', error);
    }
    
    // Create summary stats first
    html += '<div class="summary-stats">';
    html += `<div class="stat-card"><div class="stat-value">${totalStations}</div><div class="stat-label">Total Stations</div></div>`;
    html += `<div class="stat-card stat-anomaly"><div class="stat-value">${anomalousCount}</div><div class="stat-label">Anomalies Detected</div></div>`;
    html += `<div class="stat-card stat-eq-reliable"><div class="stat-value">${withEQ}</div><div class="stat-label">🌋 With EQ M≥5.5 (Reliable)</div></div>`;
    html += `<div class="stat-card stat-false-alarm"><div class="stat-value">${falseAlarms}</div><div class="stat-label">⚠️ False Alarms</div></div>`;
    html += `<div class="stat-card stat-false-negative"><div class="stat-value">${falseNegatives}</div><div class="stat-label">❌ False Negatives (M≥5.5)</div></div>`;
    html += '</div>';
    
    // Add today's earthquake statistics
    html += '<div class="today-eq-stats">';
    html += `<h3>📊 Today's Earthquakes (M≥5.5) - ${new Date().toLocaleDateString()}</h3>`;
    html += '<div class="eq-stats-grid">';
    html += `<div class="eq-stat-card"><div class="eq-stat-value">${todayEQStats.global || 0}</div><div class="eq-stat-label">🌍 Global Count</div></div>`;
    html += `<div class="eq-stat-card"><div class="eq-stat-value">${todayEQStats.within200km || 0}</div><div class="eq-stat-label">📍 Within 200km of Stations</div></div>`;
    html += '</div>';
    if (todayEQStats.global > 0 && todayEQStats.within200km === 0) {
        html += '<p class="eq-stats-note" style="color: #f39c12; margin-top: 10px; font-size: 0.9em;">ℹ️ There are earthquakes globally, but none within 200km of any station.</p>';
    } else if (todayEQStats.global === 0) {
        html += '<p class="eq-stats-note" style="color: #95a5a6; margin-top: 10px; font-size: 0.9em;">ℹ️ No earthquakes (M≥5.5) detected globally today.</p>';
    }
    html += '</div>';
    
    // Main content area: Map on top (full width), Plot panel below (full width)
    html += '<div class="main-content-layout">';
    
    // Top: Map (full width)
    html += '<div class="map-section">';
    html += '<div id="map-container" class="map-container"></div>';
    html += '<div class="map-legend">';
    html += '<h4 style="margin: 0 0 10px 0; font-size: 1.1em; color: #2c3e50;">Map Legend</h4>';
    html += '<div class="legend-item"><span class="legend-marker marker-gray"></span> Normal Station</div>';
    html += '<div class="legend-item"><span class="legend-marker marker-eq-reliable"></span> Anomaly with EQ (M≥5.5)</div>';
    html += '<div class="legend-item"><span class="legend-marker marker-eq-false"></span> False Alarm (No EQ)</div>';
    html += '<div class="legend-item"><span class="legend-marker earthquake-marker-legend"></span> Earthquake (M≥5.5)</div>';
    html += '</div>';
    html += '</div>';
    
    // Station list button (moved below map)
    html += '<div class="controls" style="margin-top: 15px; margin-bottom: 15px;">';
    html += '<button id="toggle-stations" class="btn btn-primary">📋 Show All Stations List</button>';
    html += '<div id="stations-list" class="stations-list hidden"></div>';
    html += '</div>';
    
    // Bottom: Plot panel (full width)
    html += '<div class="plot-panel-section">';
    html += '<div class="plot-panel">';
    html += '<h2 class="panel-title">📊 Station Analysis</h2>';
    html += '<div class="selector-container">';
    html += '<label for="station-selector" class="selector-label">Select Station:</label>';
    html += '<select id="station-selector" class="station-selector">';
    html += '<option value="">-- Select a station --</option>';
    
    // Add anomalous stations first
    anomalousStations.forEach(station => {
        const metadata = stationMetadata[station] || {};
        const stationData = allStationsData[station];
        const eqCorrelations = stationDataMap[station]?.eqCorrelations || [];
        const hasEQ = eqCorrelations.length > 0;
        const label = `${station} - ${metadata.name || station}${hasEQ ? ' 🌋' : ' ⚠️'}`;
        html += `<option value="${station}"${anomalousStations.indexOf(station) === 0 ? ' selected' : ''}>${label}</option>`;
    });
    
    // Add other stations
    allStations.filter(s => !anomalousStations.includes(s)).forEach(station => {
        const metadata = stationMetadata[station] || {};
        html += `<option value="${station}">${station} - ${metadata.name || station} (Normal)</option>`;
    });
    
    html += '</select>';
    html += '</div>';
    html += '<div id="selected-station-plot" class="selected-station-plot"></div>';
    html += '</div>';
    html += '</div>';
    html += '</div>'; // Close main-content-layout
    
    container.innerHTML = html;
    
    // Initialize map
    setTimeout(async () => {
        const mapEl = document.getElementById('map-container');
        if (mapEl && mapEl.offsetParent !== null) {
            try {
                initMap();
                await new Promise(resolve => setTimeout(resolve, 200));
                
                // Add all station markers
                for (const station of allStations) {
                    const { stationData, eqCorrelations } = stationDataMap[station];
                    addStationToMap(station, stationData, eqCorrelations);
                }
                
                // Add earthquake markers
                const recentEarthquakes = await loadRecentEarthquakes();
                console.log('Loaded earthquakes for map:', recentEarthquakes.length, recentEarthquakes);
                addEarthquakeMarkers(recentEarthquakes);
            } catch (error) {
                console.error('Error initializing map:', error);
            }
        }
    }, 300);
    
    // Setup station selector
    const selector = document.getElementById('station-selector');
    if (selector) {
        selector.addEventListener('change', async (e) => {
            const selectedStation = e.target.value;
            if (selectedStation) {
                await renderStationPlot(selectedStation);
            } else {
                document.getElementById('selected-station-plot').innerHTML = '';
            }
        });
        
        // Load first anomalous station by default
        if (anomalousStations.length > 0) {
            selector.value = anomalousStations[0];
            await renderStationPlot(anomalousStations[0]);
        }
    }
    
    // Setup toggle button
    const toggleBtn = document.getElementById('toggle-stations');
    const stationsList = document.getElementById('stations-list');
    if (toggleBtn && stationsList) {
        toggleBtn.addEventListener('click', () => {
            stationsList.classList.toggle('hidden');
            toggleBtn.textContent = stationsList.classList.contains('hidden') 
                ? '📋 Show All Stations List' 
                : '📋 Hide Stations List';
            if (!stationsList.classList.contains('hidden')) {
                renderStationsList(allStations, allStationsData);
            }
        });
    }
    
    // Update timestamp
    const timestampEl = document.getElementById('timestamp');
    if (timestampEl && data.last_updated) {
        timestampEl.textContent = new Date(data.last_updated).toLocaleString('en-US', {
            timeZone: 'Asia/Singapore',
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        }) + ' GMT+8';
    }
}

async function renderStationPlot(stationCode) {
    const plotDiv = document.getElementById('selected-station-plot');
    if (!plotDiv) return;
    
    plotDiv.innerHTML = '<div class="loading">Loading station data...</div>';
    
    const stationData = allStationsData[stationCode];
    const metadata = stationMetadata[stationCode] || {};
    const eqCorrelations = await loadEarthquakeCorrelations(stationCode);
    // Filter by magnitude >= 5.5 for reliability
    const reliableCorrelations = eqCorrelations.filter(eq => parseFloat(eq.earthquake_magnitude || 0) >= 5.5);
    const hasEQ = reliableCorrelations.length > 0;
    const hasAnomaly = stationData && stationData.is_anomalous;
    const falseNegatives = await loadFalseNegatives(stationCode);
    
    let html = `<div class="station-plot-card">`;
    html += `<div class="plot-header">`;
    html += `<h3>${stationCode} - ${metadata.name || stationCode}</h3>`;
    html += `<p class="plot-location">${metadata.country || ''} | 📍 ${metadata.latitude ? metadata.latitude.toFixed(3) : 'N/A'}, ${metadata.longitude ? metadata.longitude.toFixed(3) : 'N/A'}</p>`;
    
    if (hasAnomaly) {
        html += `<div class="plot-status ${hasEQ ? 'status-eq' : 'status-false'}">`;
        html += hasEQ ? `🌋 EQ Correlation Found (M≥5.5): ${reliableCorrelations.length}` : `⚠️ False Alarm (No EQ M≥5.5)`;
        html += `</div>`;
    } else {
        html += `<div class="plot-status status-normal">✅ Normal</div>`;
        if (falseNegatives.length > 0) {
            html += `<div class="plot-status status-false-negative" style="margin-top: 8px;">❌ False Negative: ${falseNegatives.length} EQ M≥5.5 without anomaly</div>`;
        }
    }
    html += `</div>`;
    
    // Load and display figure
    const figures = await loadStationFigures(stationCode);
    if (figures.length > 0) {
        html += `<div class="plot-image-container">`;
        html += `<img src="figures/${stationCode}/${figures[0]}" alt="PRA Plot for ${stationCode}" class="plot-image" onerror="this.parentElement.innerHTML='<p class=\\'error\\'>Plot not available</p>'">`;
        html += `</div>`;
    } else {
        html += `<div class="no-plot">Plot not available for this station</div>`;
    }
    
    // Add station info
    if (stationData) {
        html += `<div class="plot-info">`;
        html += `<div class="info-row"><span class="info-label">Date:</span><span class="info-value">${formatDate(stationData.date)}</span></div>`;
        html += `<div class="info-row"><span class="info-label">Threshold:</span><span class="info-value">${parseFloat(stationData.threshold || 0).toFixed(2)}</span></div>`;
        html += `<div class="info-row"><span class="info-label">Anomaly Hours:</span><span class="info-value">${stationData.nAnomHours || 0}</span></div>`;
        // Show reliable correlations (M>=5.5)
        if (hasEQ && reliableCorrelations.length > 0) {
            html += `<div class="eq-info">`;
            html += `<h4>🌋 Earthquake Correlations (M≥5.5):</h4>`;
            reliableCorrelations.slice(0, 5).forEach((eq) => {
                const mag = eq.earthquake_magnitude || 'N/A';
                const dist = parseFloat(eq.earthquake_distance_km || 0).toFixed(1);
                const days = parseFloat(eq.days_before_anomaly || 0).toFixed(1);
                html += `<div class="eq-item">M${mag} @ ${dist}km (${days} days before)</div>`;
            });
            html += `</div>`;
        }
        
        // Show false negatives if any
        if (falseNegatives.length > 0) {
            html += `<div class="fn-info">`;
            html += `<h4>❌ False Negatives (M≥5.5, no anomaly detected):</h4>`;
            falseNegatives.slice(0, 3).forEach((fn) => {
                const mag = fn.earthquake_magnitude || 'N/A';
                const dist = parseFloat(fn.earthquake_distance_km || 0).toFixed(1);
                const date = fn.earthquake_time ? formatDate(fn.earthquake_time) : 'Unknown';
                html += `<div class="fn-item">M${mag} @ ${dist}km on ${date}</div>`;
            });
            if (falseNegatives.length > 3) {
                html += `<div class="fn-item">... and ${falseNegatives.length - 3} more</div>`;
            }
            html += `</div>`;
        }
        html += `</div>`;
    }
    
    html += `</div>`;
    plotDiv.innerHTML = html;
}

async function loadStationFigures(station) {
    try {
        const response = await fetch(`data/${station}_latest.json`);
        if (response.ok) {
            const data = await response.json();
            if (data.date) {
                const dateStr = data.date.replace(/-/g, '');
                return [`PRA_${station}_${dateStr}.png`];
            }
        }
    } catch (e) {}
    return [];
}

async function renderStationsList(stations, stationsData) {
    const listEl = document.getElementById('stations-list');
    if (!listEl) return;
    
    let html = '<table class="stations-table"><thead><tr>';
    html += '<th>Code</th><th>Name</th><th>Country</th><th>Status</th><th>🌋 EQ Correlation</th>';
    html += '</tr></thead><tbody>';
    
    for (const station of stations) {
        const metadata = stationMetadata[station] || {};
        const data = stationsData && stationsData[station];
        const hasAnomaly = data && data.is_anomalous;
        const eqCorrelations = await loadEarthquakeCorrelations(station);
        const hasEQ = eqCorrelations.length > 0;
        
        html += '<tr>';
        html += `<td><strong>${station}</strong></td>`;
        html += `<td>${metadata.name || station}</td>`;
        html += `<td>${metadata.country || '-'}</td>`;
        
        if (hasAnomaly) {
            html += `<td><span class="badge badge-danger">⚠️ Anomaly</span></td>`;
            html += `<td>${hasEQ ? '<span class="badge badge-eq">🌋 Yes (' + eqCorrelations.length + ')</span>' : '<span class="badge badge-warning">⚠️ No (False Alarm)</span>'}</td>`;
        } else {
            html += `<td><span class="badge badge-secondary">✅ Normal</span></td>`;
            html += `<td>-</td>`;
        }
        
        html += '</tr>';
    }
    
    html += '</tbody></table>';
    listEl.innerHTML = html;
}
