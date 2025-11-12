// Enhanced frontend JavaScript for PRA Dashboard with Map

const DATA_URL = 'data/stations.json';
const STATIONS_METADATA_URL = 'data/stations.json'; // Station metadata (same file, different structure)

let allStationsData = {};
let stationMetadata = {};
let map = null;
let markers = {};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadStationMetadata();
    renderDashboard();
    
    // Auto-refresh every 5 minutes
    setInterval(renderDashboard, 300000);
});

async function loadStationMetadata() {
    try {
        const response = await fetch(DATA_URL);
        if (response.ok) {
            const data = await response.json();
            stationMetadata = {};
            // Try metadata array first (from upload_results.py)
            if (data.metadata && Array.isArray(data.metadata)) {
                data.metadata.forEach(station => {
                    stationMetadata[station.code] = station;
                });
            } else if (data.stations && Array.isArray(data.stations)) {
                // Fallback: check if stations array has metadata format
                data.stations.forEach(station => {
                    if (typeof station === 'object' && station.code) {
                        stationMetadata[station.code] = station;
                    }
                });
            }
        }
    } catch (error) {
        console.error('Error loading station metadata:', error);
    }
}

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

function formatTime(timeStr) {
    const date = new Date(timeStr);
    return date.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit'
    });
}

function initMap() {
    // Check if map container exists
    const mapContainer = document.getElementById('map-container');
    if (!mapContainer) {
        console.error('Map container not found');
        return;
    }
    
    // Initialize Leaflet map
    if (map) {
        try {
            map.remove();
        } catch (e) {
            // Map might already be removed
        }
    }
    
    try {
        map = L.map('map-container').setView([20, 0], 2);
        
        // Add OpenStreetMap tiles
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 18
        }).addTo(map);
        
        // Clear existing markers
        Object.values(markers).forEach(marker => {
            try {
                marker.remove();
            } catch (e) {
                // Marker might already be removed
            }
        });
        markers = {};
    } catch (error) {
        console.error('Error creating map:', error);
        throw error;
    }
}

function addStationToMap(stationCode, stationData, eqCorrelations) {
    // Check if map is initialized
    if (!map) {
        console.warn('Map not initialized, skipping marker for', stationCode);
        return;
    }
    
    const metadata = stationMetadata[stationCode];
    if (!metadata || !metadata.latitude || !metadata.longitude) {
        return;
    }
    
    const hasAnomaly = stationData && stationData.is_anomalous;
    const hasEQ = eqCorrelations && eqCorrelations.length > 0;
    
    // Determine marker color
    let color = 'gray'; // No anomaly
    if (hasAnomaly) {
        color = hasEQ ? 'green' : 'red'; // Green if EQ found, red if false alarm
    }
    
    // Create custom icon
    const icon = L.divIcon({
        className: 'station-marker',
        html: `<div class="marker-dot marker-${color}"></div>`,
        iconSize: [20, 20],
        iconAnchor: [10, 10]
    });
    
    // Create popup content
    let popupContent = `<div style="min-width: 200px;"><strong>${metadata.name || stationCode} (${stationCode})</strong><br>`;
    popupContent += `${metadata.country || 'Unknown'}<br>`;
    popupContent += `Coordinates: ${metadata.latitude ? metadata.latitude.toFixed(3) : 'N/A'}, ${metadata.longitude ? metadata.longitude.toFixed(3) : 'N/A'}<br>`;
    
    if (hasAnomaly && stationData) {
        popupContent += `<hr><strong style="color: #e74c3c;">⚠ Anomaly Detected</strong><br>`;
        popupContent += `Date: ${formatDate(stationData.date)}<br>`;
        popupContent += `Threshold: ${parseFloat(stationData.threshold || 0).toFixed(2)}<br>`;
        popupContent += `Anomaly Hours: ${stationData.nAnomHours || 0}<br>`;
        
        if (hasEQ && eqCorrelations.length > 0) {
            popupContent += `<hr><strong style="color: #27ae60;">✓ EQ Correlation Found (Reliable)</strong><br>`;
            eqCorrelations.slice(0, 3).forEach((eq) => {
                const mag = eq.earthquake_magnitude || 'N/A';
                const dist = parseFloat(eq.earthquake_distance_km || 0).toFixed(1);
                const days = parseFloat(eq.days_before_anomaly || 0).toFixed(1);
                popupContent += `M${mag} @ ${dist}km (${days} days before)<br>`;
            });
            if (eqCorrelations.length > 3) {
                popupContent += `... and ${eqCorrelations.length - 3} more<br>`;
            }
        } else {
            popupContent += `<hr><strong style="color: #f39c12;">⚠ False Alarm</strong><br>`;
            popupContent += `No EQ within 200km<br>`;
            popupContent += `within 14 days`;
        }
    } else {
        popupContent += `<hr><span style="color: #95a5a6;">Status: Normal</span><br>`;
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
    
    container.innerHTML = '<p>Loading data...</p>';
    
    const data = await loadData();
    if (!data) {
        container.innerHTML = '<p class="no-data">❌ Failed to load data. Make sure to run upload_results.py first.</p>';
        return;
    }
    
    const stations = data.stations || [];
    let html = '';
    
    // Create station list button
    html += '<div class="controls">';
    html += '<button id="toggle-stations" class="btn btn-primary">Show All Stations List</button>';
    html += '<div id="stations-list" class="stations-list hidden"></div>';
    html += '</div>';
    
    // Create map container
    html += '<div id="map-container" class="map-container"></div>';
    
    // Create summary stats
    let totalStations = 0;
    let anomalousStations = 0;
    let withEQ = 0;
    let falseAlarms = 0;
    
    // Process stations and count stats (don't add to map yet - map not initialized)
    const stationDataMap = {};
    for (const station of stations) {
        const stationData = data.data && data.data[station];
        const hasAnomaly = stationData && stationData.is_anomalous;
        
        if (hasAnomaly) {
            anomalousStations++;
            // Load earthquake correlations
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
        totalStations++;
    }
    
    // Add summary
    html += '<div class="summary-stats">';
    html += `<div class="stat-card"><div class="stat-value">${totalStations}</div><div class="stat-label">Total Stations</div></div>`;
    html += `<div class="stat-card"><div class="stat-value">${anomalousStations}</div><div class="stat-label">Anomalies Detected</div></div>`;
    html += `<div class="stat-card stat-success"><div class="stat-value">${withEQ}</div><div class="stat-label">With EQ (Reliable)</div></div>`;
    html += `<div class="stat-card stat-warning"><div class="stat-value">${falseAlarms}</div><div class="stat-label">False Alarms</div></div>`;
    html += '</div>';
    
    // Station cards
    html += '<div class="stations-grid">';
    for (const station of stations) {
        html += createStationCard(station, data.data && data.data[station]);
    }
    html += '</div>';
    
    container.innerHTML = html;
    
    // Initialize map after DOM update - wait for HTML to be fully rendered
    setTimeout(async () => {
        const mapEl = document.getElementById('map-container');
        if (mapEl) {
            // Map container exists, initialize map
            if (!map) {
                try {
                    initMap();
                } catch (error) {
                    console.error('Error initializing map:', error);
                    return;
                }
            }
            
            // Wait a bit for map to be fully ready
            await new Promise(resolve => setTimeout(resolve, 100));
            
            // Now add all markers
            for (const station of stations) {
                const { stationData, eqCorrelations } = stationDataMap[station];
                addStationToMap(station, stationData, eqCorrelations);
            }
        } else {
            // Retry if map container not ready
            setTimeout(async () => {
                const mapEl2 = document.getElementById('map-container');
                if (mapEl2) {
                    if (!map) {
                        try {
                            initMap();
                        } catch (error) {
                            console.error('Error initializing map (retry):', error);
                            return;
                        }
                    }
                    await new Promise(resolve => setTimeout(resolve, 100));
                    for (const station of stations) {
                        const { stationData, eqCorrelations } = stationDataMap[station];
                        addStationToMap(station, stationData, eqCorrelations);
                    }
                }
            }, 1000);
        }
    }, 300);
    
    // Setup toggle button
    const toggleBtn = document.getElementById('toggle-stations');
    const stationsList = document.getElementById('stations-list');
    if (toggleBtn && stationsList) {
        toggleBtn.addEventListener('click', () => {
            stationsList.classList.toggle('hidden');
            toggleBtn.textContent = stationsList.classList.contains('hidden') 
                ? 'Show All Stations List' 
                : 'Hide Stations List';
            renderStationsList(stations, data.data);
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

async function renderStationsList(stations, stationsData) {
    const listEl = document.getElementById('stations-list');
    if (!listEl) return;
    
    let html = '<table class="stations-table"><thead><tr>';
    html += '<th>Code</th><th>Name</th><th>Country</th><th>Status</th><th>EQ Correlation</th>';
    html += '</tr></thead><tbody>';
    
    // Process stations asynchronously
    for (const station of stations) {
        const metadata = stationMetadata[station] || {};
        const data = stationsData && stationsData[station];
        const hasAnomaly = data && data.is_anomalous;
        const eqCorrelations = await loadEarthquakeCorrelations(station);
        const hasEQ = eqCorrelations.length > 0;
        
        html += '<tr>';
        html += `<td>${station}</td>`;
        html += `<td>${metadata.name || station}</td>`;
        html += `<td>${metadata.country || '-'}</td>`;
        
        if (hasAnomaly) {
            html += `<td><span class="badge badge-danger">Anomaly</span></td>`;
            html += `<td>${hasEQ ? '<span class="badge badge-success">Yes</span>' : '<span class="badge badge-warning">No (False Alarm)</span>'}</td>`;
        } else {
            html += `<td><span class="badge badge-secondary">Normal</span></td>`;
            html += `<td>-</td>`;
        }
        
        html += '</tr>';
    }
    
    html += '</tbody></table>';
    listEl.innerHTML = html;
}

function createStationCard(station, stationData) {
    const hasData = stationData && stationData.is_anomalous !== undefined;
    const results = stationData;
    const metadata = stationMetadata[station] || {};
    
    let cardHTML = `
        <div class="station-card">
            <h2>Station: ${station}</h2>
            <p class="station-location">${metadata.name || station}, ${metadata.country || ''}</p>
    `;
    
    if (hasData && results) {
        const isAnomalous = results.is_anomalous || false;
        const nAnomHours = results.nAnomHours || 0;
        const threshold = results.threshold || 0;
        const date = results.date || 'Unknown';
        
        // Load earthquake correlations
        loadEarthquakeCorrelations(station).then(eqCorrelations => {
            const hasEQ = eqCorrelations.length > 0;
            const eqBadge = document.getElementById(`eq-badge-${station}`);
            if (eqBadge) {
                if (hasEQ) {
                    eqBadge.innerHTML = `<span class="badge badge-success">✓ EQ Correlation Found (${eqCorrelations.length})</span>`;
                } else if (isAnomalous) {
                    eqBadge.innerHTML = `<span class="badge badge-warning">⚠ False Alarm (No EQ)</span>`;
                }
            }
        });
        
        cardHTML += `
            <div class="status-badge ${isAnomalous ? 'anomaly' : 'normal'}">
                ${isAnomalous ? `⚠️ Anomaly Detected (${nAnomHours} hours)` : '✅ Normal'}
            </div>
            
            <div id="eq-badge-${station}"></div>
            
            <div class="info-box">
                <p><strong>Date:</strong> ${date}</p>
                <p><strong>Threshold:</strong> ${threshold.toFixed(2)}</p>
                <p><strong>Data Points:</strong> ${results.P ? results.P.length : 0}</p>
                ${metadata.latitude ? `<p><strong>Coordinates:</strong> ${metadata.latitude.toFixed(3)}, ${metadata.longitude.toFixed(3)}</p>` : ''}
            </div>
        `;
        
        // Add figure
        cardHTML += `
            <div class="figure-section">
                <h3>Latest Plot</h3>
                <div id="figure-${station}">
                    <p>Loading plot...</p>
                </div>
            </div>
        `;
        
        // Load figure asynchronously
        loadStationFigures(station).then(figures => {
            const figureDiv = document.getElementById(`figure-${station}`);
            if (figures.length > 0 && figureDiv) {
                const latestFig = figures[0];
                figureDiv.innerHTML = `
                    <img src="figures/${station}/${latestFig}" 
                         alt="PRA Plot for ${station}" 
                         class="plot-image"
                         onerror="this.parentElement.innerHTML='<p>Plot not available</p>'">
                `;
            } else if (figureDiv) {
                figureDiv.innerHTML = '<p>Plot not available</p>';
            }
        });
        
        // Add anomalies table
        getStationAnomalies(station).then(anomalies => {
            const anomaliesDiv = document.getElementById(`anomalies-${station}`);
            if (anomalies && anomalies.length > 0 && anomaliesDiv) {
                let tableHTML = `
                    <div class="anomalies-section">
                        <h3>Recent Anomalies (Last 10)</h3>
                        <div class="table-container">
                            <table class="anomaly-table">
                                <thead>
                                    <tr>
                                        <th>Date Range</th>
                                        <th>Time</th>
                                        <th>Threshold</th>
                                        <th>PRA Values</th>
                                        <th>EQ Correlation</th>
                                    </tr>
                                </thead>
                                <tbody>
                `;
                
                anomalies.slice(0, 10).forEach(anomaly => {
                    // Check for EQ correlation
                    loadEarthquakeCorrelations(station).then(eqCorrelations => {
                        const hasEQ = eqCorrelations.some(eq => 
                            eq.anomaly_range === anomaly.Range
                        );
                        const eqStatus = hasEQ ? 
                            '<span class="badge badge-success">Yes</span>' : 
                            '<span class="badge badge-warning">No</span>';
                        
                        tableHTML += `
                            <tr>
                                <td>${anomaly.Range || '-'}</td>
                                <td>${anomaly.Times || '-'}</td>
                                <td>${anomaly.Threshold ? parseFloat(anomaly.Threshold).toFixed(2) : '-'}</td>
                                <td>${anomaly.PRA || '-'}</td>
                                <td>${eqStatus}</td>
                            </tr>
                        `;
                    });
                });
                
                tableHTML += `
                                </tbody>
                            </table>
                        </div>
                    </div>
                `;
                anomaliesDiv.innerHTML = tableHTML;
            }
        });
        
        cardHTML += `<div id="anomalies-${station}"></div>`;
        
    } else {
        cardHTML += `
            <div class="no-data">
                <p>⚠️ No data available for this station yet.</p>
                <p>Run the analysis script to generate results.</p>
            </div>
        `;
    }
    
    cardHTML += '</div>';
    return cardHTML;
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
    } catch (e) {
        // Ignore errors
    }
    return [];
}

async function getStationAnomalies(station) {
    try {
        const response = await fetch(`data/${station}_anomalies.csv`);
        if (!response.ok) {
            return [];
        }
        const text = await response.text();
        return parseCSV(text);
    } catch (error) {
        console.error(`Error loading anomalies for ${station}:`, error);
        return [];
    }
}
