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
        
        if (hasEQ && eqCorrelations.length > 0) {
            popupContent += `<hr style="margin: 8px 0; border-color: #e67e22;"><strong style="color: #e67e22;">🌋 EQ Correlation Found (${eqCorrelations.length})</strong><br>`;
            eqCorrelations.slice(0, 3).forEach((eq) => {
                const mag = eq.earthquake_magnitude || 'N/A';
                const dist = parseFloat(eq.earthquake_distance_km || 0).toFixed(1);
                const days = parseFloat(eq.days_before_anomaly || 0).toFixed(1);
                popupContent += `🔴 M${mag} @ ${dist}km (${days} days before)<br>`;
            });
            if (eqCorrelations.length > 3) {
                popupContent += `... and ${eqCorrelations.length - 3} more<br>`;
            }
        } else {
            popupContent += `<hr style="margin: 8px 0; border-color: #e74c3c;"><strong style="color: #e74c3c;">⚠️ False Alarm</strong><br>`;
            popupContent += `No EQ within 200km within 14 days`;
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
    
    const stationDataMap = {};
    for (const station of allStations) {
        totalStations++;
        const stationData = allStationsData[station];
        const hasAnomaly = stationData && stationData.is_anomalous;
        
        if (hasAnomaly) {
            anomalousCount++;
            anomalousStations.push(station);
            const eqCorrelations = await loadEarthquakeCorrelations(station);
            if (eqCorrelations.length > 0) {
                withEQ++;
            } else {
                falseAlarms++;
            }
            stationDataMap[station] = { stationData, eqCorrelations };
        } else {
            stationDataMap[station] = { stationData: null, eqCorrelations: [] };
        }
    }
    
    let html = '';
    
    // Create summary stats first
    html += '<div class="summary-stats">';
    html += `<div class="stat-card"><div class="stat-value">${totalStations}</div><div class="stat-label">Total Stations</div></div>`;
    html += `<div class="stat-card stat-anomaly"><div class="stat-value">${anomalousCount}</div><div class="stat-label">Anomalies Detected</div></div>`;
    html += `<div class="stat-card stat-eq-reliable"><div class="stat-value">${withEQ}</div><div class="stat-label">🌋 With EQ (Reliable)</div></div>`;
    html += `<div class="stat-card stat-false-alarm"><div class="stat-value">${falseAlarms}</div><div class="stat-label">⚠️ False Alarms</div></div>`;
    html += '</div>';
    
    // Station list button
    html += '<div class="controls">';
    html += '<button id="toggle-stations" class="btn btn-primary">📋 Show All Stations List</button>';
    html += '<div id="stations-list" class="stations-list hidden"></div>';
    html += '</div>';
    
    // Main content area: Map on top, Plot panel below (full width)
    html += '<div class="main-content-layout">';
    
    // Map section
    html += '<div class="map-section">';
    html += '<div id="map-container" class="map-container"></div>';
    html += '<div class="map-legend">';
    html += '<div class="legend-item"><span class="legend-marker marker-gray"></span> Normal Station</div>';
    html += '<div class="legend-item"><span class="legend-marker marker-eq-reliable"></span> Anomaly with EQ Correlation</div>';
    html += '<div class="legend-item"><span class="legend-marker marker-eq-false"></span> False Alarm (No EQ)</div>';
    html += '</div>';
    html += '</div>';
    
    // Plot panel section - Full width below map
    html += '<div class="plot-panel-section">';
    html += '<div class="plot-panel">';
    html += '<h2 class="panel-title">📊 Station Analysis Plot</h2>';
    html += '<p class="panel-description">Select a station from the dropdown below to view detailed analysis plots, anomaly information, and earthquake correlations. Anomalous stations are listed first.</p>';
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
                
                // Add all markers
                for (const station of allStations) {
                    const { stationData, eqCorrelations } = stationDataMap[station];
                    addStationToMap(station, stationData, eqCorrelations);
                }
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
    const hasEQ = eqCorrelations.length > 0;
    const hasAnomaly = stationData && stationData.is_anomalous;
    
    let html = `<div class="station-plot-card">`;
    html += `<div class="plot-header">`;
    html += `<h3>${stationCode} - ${metadata.name || stationCode}</h3>`;
    html += `<p class="plot-location">${metadata.country || ''} | 📍 ${metadata.latitude ? metadata.latitude.toFixed(3) : 'N/A'}, ${metadata.longitude ? metadata.longitude.toFixed(3) : 'N/A'}</p>`;
    
    if (hasAnomaly) {
        html += `<div class="plot-status ${hasEQ ? 'status-eq' : 'status-false'}">`;
        html += hasEQ ? `🌋 EQ Correlation Found (${eqCorrelations.length})` : `⚠️ False Alarm (No EQ)`;
        html += `</div>`;
    } else {
        html += `<div class="plot-status status-normal">✅ Normal</div>`;
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
        if (hasEQ && eqCorrelations.length > 0) {
            html += `<div class="eq-info">`;
            html += `<h4>🌋 Earthquake Correlations:</h4>`;
            eqCorrelations.slice(0, 5).forEach((eq) => {
                const mag = eq.earthquake_magnitude || 'N/A';
                const dist = parseFloat(eq.earthquake_distance_km || 0).toFixed(1);
                const days = parseFloat(eq.days_before_anomaly || 0).toFixed(1);
                html += `<div class="eq-item">M${mag} @ ${dist}km (${days} days before)</div>`;
            });
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
