// Enhanced frontend JavaScript for PRA Dashboard with Map - Earthquake Theme

const DATA_URL = 'data/stations.json';

let allStationsData = {};
let stationMetadata = {};
let map = null;
let markers = {};
let allStations = [];
let anomalousStations = [];
let availableDates = [];
let selectedDate = null;
let mostRecentDate = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Set up dark mode toggle
    const darkModeToggle = document.getElementById('dark-mode-toggle');
    if (darkModeToggle) {
        // Load saved preference
        const savedMode = localStorage.getItem('darkMode');
        if (savedMode === 'true') {
            document.body.classList.add('dark-mode');
            darkModeToggle.checked = true;
        }
        
        darkModeToggle.addEventListener('change', (e) => {
            if (e.target.checked) {
                document.body.classList.add('dark-mode');
                localStorage.setItem('darkMode', 'true');
            } else {
                document.body.classList.remove('dark-mode');
                localStorage.setItem('darkMode', 'false');
            }
        });
    }
    
    // Set up date selector
    const dateSelector = document.getElementById('date-selector');
    if (dateSelector) {
        dateSelector.addEventListener('change', (e) => {
            const newDate = e.target.value;
            if (newDate) {
                selectedDate = newDate; // Update global variable
                renderDashboard(newDate);
            }
        });
    }
    
    // Set up CSV download button
    const downloadBtn = document.getElementById('download-anomalies-btn');
    if (downloadBtn) {
        downloadBtn.addEventListener('click', downloadAnomaliesCSV);
    }
    
    // Populate date selector immediately from stations.json
    populateDateSelectorFromMetadata().then(() => {
        // Wait a bit for date selector to populate, then render
        setTimeout(() => {
            renderDashboard();
        }, 100);
    }).catch(error => {
        console.error('Error populating date selector:', error);
        // Still try to render even if date selector fails
        renderDashboard();
    });
    setInterval(() => {
        // Auto-refresh with current selected date
        const currentDate = document.getElementById('date-selector')?.value || selectedDate;
        renderDashboard(currentDate);
    }, 300000); // Auto-refresh every 5 minutes
});

async function loadData(date = null) {
    try {
        // First, load stations.json to get available dates
        const response = await fetch(DATA_URL);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const metadata = await response.json();
        
        // Extract available dates and most recent date
        availableDates = metadata.available_dates || [];
        mostRecentDate = metadata.most_recent_date || null;
        
        // If no date specified, use most recent
        if (!date && mostRecentDate) {
            date = mostRecentDate;
            selectedDate = date;
        } else if (!date) {
            // Fallback to today if no dates available
            date = new Date().toISOString().split('T')[0];
            selectedDate = date;
        } else {
            selectedDate = date;
        }
        
        // Validate that the selected date is in available dates
        // If not, use the most recent date instead
        if (availableDates.length > 0 && !availableDates.includes(date)) {
            console.warn(`Selected date ${date} not in available dates. Using most recent: ${mostRecentDate}`);
            date = mostRecentDate || availableDates[0];
            selectedDate = date;
        }
        
        // Load data for the selected date, with station-specific fallback to previous days
        // Only try dates that are in available_dates to avoid unnecessary 404s
        const dateData = {};
        const stationDates = {}; // Track which date each station is using
        let hasAnyData = false;
        
        // Sort available dates in descending order (most recent first) for efficient fallback
        const sortedAvailableDates = [...availableDates].sort().reverse();
        
        // For each station, try to load data for selected date first
        // If not available, fallback to most recent available date (for map display)
        // This allows the map to show the most recent data even if selected date doesn't have data
        for (const station of (metadata.stations || [])) {
            let stationData = null;
            let stationDateUsed = null;
            
            // First, try the selected date (if it's in available_dates)
            if (availableDates.includes(date)) {
                try {
                    const stationResponse = await fetch(`data/${station}_${date}.json`);
                    if (stationResponse.ok) {
                        stationData = await stationResponse.json();
                        stationDateUsed = date;
                        hasAnyData = true;
                    }
                } catch (error) {
                    // Continue to fallback
                }
            }
            
            // If selected date doesn't have data, fallback to most recent available date
            // This ensures the map always shows the most recent data
            if (!stationData && sortedAvailableDates.length > 0) {
                for (const tryDate of sortedAvailableDates) {
                    // Skip if we already tried this date
                    if (tryDate === date) continue;
                    
                    try {
                        const stationResponse = await fetch(`data/${station}_${tryDate}.json`);
                        if (stationResponse.ok) {
                            stationData = await stationResponse.json();
                            stationDateUsed = tryDate;
                            hasAnyData = true;
                            console.debug(`Station ${station}: Using fallback data from ${tryDate} (selected date ${date} not available)`);
                            break; // Found data, stop trying
                        }
                    } catch (error) {
                        continue;
                    }
                }
            }
            
            // Store station data and date used
            if (stationData) {
                dateData[station] = stationData;
                stationDates[station] = stationDateUsed;
            }
        }
        
        // If no data found for any station, return null
        if (!hasAnyData) {
            return null;
        }
        
        // Return data in the same format as before
        return {
            stations: metadata.stations || [],
            data: dateData,
            metadata: metadata.metadata || [],
            available_dates: availableDates,
            most_recent_date: mostRecentDate,
            selected_date: date,
            station_dates: stationDates  // Which date each station is using
        };
    } catch (error) {
        console.error('Error loading data:', error);
        return null;
    }
}

async function loadEarthquakeCorrelations(station, date = null) {
    try {
        // Try date-specific file first if date is provided
        if (date) {
            try {
                const dateResponse = await fetch(`data/${station}_${date}_earthquake_correlations.json`);
                if (dateResponse.ok) {
                    const data = await dateResponse.json();
                    // Handle both array and object formats
                    const correlations = Array.isArray(data) ? data : (data.correlations || []);
                    // Filter by magnitude >= 5.0 for reliability
                    return correlations.filter(eq => parseFloat(eq.earthquake_magnitude || eq.magnitude || 0) >= 5.0);
                }
            } catch (error) {
                // Fallback to CSV
            }
        }
        
        // Fallback to static CSV file
        const response = await fetch(`data/${station}_earthquake_correlations.csv`);
        if (!response.ok) {
            // Silently return empty array if CSV doesn't exist
            return [];
        }
        const text = await response.text();
        const correlations = parseCSV(text);
        // Filter by magnitude >= 5.0 for reliability
        return correlations.filter(eq => parseFloat(eq.earthquake_magnitude || 0) >= 5.0);
    } catch (error) {
        // Silently return empty array - CSV files are optional
        return [];
    }
}

async function loadFalseNegatives(station, date = null) {
    try {
        // Try date-specific file first if date is provided
        if (date) {
            try {
                const dateResponse = await fetch(`data/${station}_${date}_false_negatives.json`);
                if (dateResponse.ok) {
                    const data = await dateResponse.json();
                    // Handle both array and object formats
                    return Array.isArray(data) ? data : (data.false_negatives || []);
                }
            } catch (error) {
                // Fallback to CSV
            }
        }
        
        // Fallback to static CSV file
        const response = await fetch(`data/${station}_false_negatives.csv`);
        if (!response.ok) {
            // Silently return empty array if CSV doesn't exist
            return [];
        }
        const text = await response.text();
        return parseCSV(text);
    } catch (error) {
        // Silently return empty array - CSV files are optional
        return [];
    }
}

async function loadRecentEarthquakes(date = null) {
    // Load earthquake data for the specified date only (no fallback)
    // Use selectedDate if no date provided
    if (!date) {
        date = selectedDate || new Date().toISOString().split('T')[0];
    }
    
    // Only try the specified date
    try {
        const response = await fetch(`data/recent_earthquakes_${date}.csv`);
        if (response.ok) {
            const text = await response.text();
            return parseCSV(text);
        }
    } catch (error) {
        // Return empty array if file doesn't exist
    }
    
    return [];
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

function formatDateForSelector(dateStr) {
    const date = new Date(dateStr + 'T00:00:00');
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    
    const dateOnly = new Date(date);
    dateOnly.setHours(0, 0, 0, 0);
    
    let label = date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
    
    if (dateOnly.getTime() === today.getTime()) {
        label += ' (Today)';
    } else if (dateOnly.getTime() === yesterday.getTime()) {
        label += ' (Yesterday)';
    }
    
    return label;
}

async function populateDateSelectorFromMetadata() {
    try {
        const response = await fetch(DATA_URL);
        if (!response.ok) {
            console.error('Failed to load stations.json:', response.status);
            return;
        }
        const metadata = await response.json();
        
        const dateSelector = document.getElementById('date-selector');
        if (dateSelector && metadata.available_dates && metadata.available_dates.length > 0) {
            dateSelector.innerHTML = '';
            metadata.available_dates.forEach(date => {
                const option = document.createElement('option');
                option.value = date;
                option.textContent = formatDateForSelector(date);
                if (date === metadata.most_recent_date) {
                    option.selected = true;
                    selectedDate = date;
                }
                dateSelector.appendChild(option);
            });
            
            // Store for later use
            availableDates = metadata.available_dates || [];
            mostRecentDate = metadata.most_recent_date || null;
        }
    } catch (error) {
        console.error('Error populating date selector:', error);
    }
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
        
        // Clear existing markers and circles
        if (markers.earthquakes) {
            markers.earthquakes.forEach(m => {
                try { m.remove(); } catch (e) {}
            });
        }
        if (markers.earthquakeCircles) {
            markers.earthquakeCircles.forEach(c => {
                try { c.remove(); } catch (e) {}
            });
        }
        Object.keys(markers).forEach(key => {
            if (key !== 'earthquakes' && key !== 'earthquakeCircles') {
                try {
                    if (Array.isArray(markers[key])) {
                        markers[key].forEach(m => m.remove());
                    } else {
                        markers[key].remove();
                    }
                } catch (e) {}
            }
        });
        markers = {};
    } catch (error) {
        console.error('Error creating map:', error);
    }
}

function addStationToMap(stationCode, stationData, eqCorrelations, dataContext = null) {
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
    
    // Get the date being used for this station (from stationData or station_dates)
    const stationDateUsed = stationData?.date || (dataContext?.station_dates && dataContext.station_dates[stationCode]) || 'Unknown';
    const isUsingFallback = dataContext?.selected_date && stationDateUsed !== dataContext.selected_date;
    
    // Create popup content with earthquake info
    let popupContent = `<div style="min-width: 220px; font-family: Arial, sans-serif;"><strong style="color: #c0392b; font-size: 1.1em;">${metadata.name || stationCode} (${stationCode})</strong><br>`;
    popupContent += `<span style="color: #7f8c8d;">${metadata.country || 'Unknown'}</span><br>`;
    popupContent += `<small>📍 ${metadata.latitude ? metadata.latitude.toFixed(3) : 'N/A'}, ${metadata.longitude ? metadata.longitude.toFixed(3) : 'N/A'}</small><br>`;
    
    // Show data date with fallback indicator
    if (isUsingFallback && dataContext?.selected_date) {
        popupContent += `<hr style="margin: 8px 0; border-color: #f39c12;">`;
        popupContent += `<small style="color: #f39c12;">📅 Data from: ${formatDate(stationDateUsed)}</small><br>`;
        popupContent += `<small style="color: #f39c12; font-style: italic;">(Selected: ${formatDateForSelector(dataContext.selected_date)})</small><br>`;
    } else if (stationData) {
        popupContent += `<hr style="margin: 8px 0; border-color: #95a5a6;">`;
        popupContent += `<small style="color: #95a5a6;">📅 Data from: ${formatDate(stationDateUsed)}</small><br>`;
    }
    
    if (hasAnomaly && stationData) {
        popupContent += `<hr style="margin: 8px 0; border-color: #e74c3c;"><strong style="color: #e74c3c;">⚠️ Anomaly Detected</strong><br>`;
        popupContent += `📅 ${formatDate(stationData.date)}<br>`;
        popupContent += `📊 Threshold: ${parseFloat(stationData.threshold || 0).toFixed(2)}<br>`;
        popupContent += `⏱️ Anomaly Hours: ${stationData.nAnomHours || 0}<br>`;
        
        // Filter by magnitude >= 5.0 for display
        const reliableCorrelations = eqCorrelations.filter(eq => parseFloat(eq.earthquake_magnitude || 0) >= 5.0);
        if (hasEQ && reliableCorrelations.length > 0) {
            popupContent += `<hr style="margin: 8px 0; border-color: #e67e22;"><strong style="color: #e67e22;">🌋 EQ Correlation Found (M≥5.0): ${reliableCorrelations.length}</strong><br>`;
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
            popupContent += `No EQ M≥5.0 within 200km within 14 days`;
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
        
        // Create popup with UTC and local time
        let timeStr = 'Unknown';
        let utcTimeStr = '';
        let localTimeStr = '';
        
        if (time) {
            try {
                // Parse time (could be ISO string or timestamp)
                const eqTime = new Date(time);
                if (!isNaN(eqTime.getTime())) {
                    // Format UTC time
                    utcTimeStr = eqTime.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
                    
                    // Format local time (at earthquake location - approximate using longitude)
                    // Rough timezone estimate: 1 hour per 15 degrees longitude
                    const localOffset = Math.round(lon / 15);
                    const localTime = new Date(eqTime.getTime() + localOffset * 3600000);
                    localTimeStr = localTime.toLocaleString('en-US', {
                        year: 'numeric',
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                        timeZoneName: 'short'
                    });
                    
                    timeStr = `${utcTimeStr}<br><small style="color: #666;">Local (approx): ${localTimeStr}</small>`;
                }
            } catch (e) {
                timeStr = time;
            }
        }
        
        const popupContent = `
            <div style="min-width: 200px; font-family: Arial, sans-serif;">
                <strong style="color: #e74c3c; font-size: 1.2em;">🌋 Earthquake M${mag.toFixed(1)}</strong><br>
                <span style="color: #555;">${place}</span><br>
                <small>📅 ${timeStr}</small><br>
                <small>📍 ${lat.toFixed(3)}, ${lon.toFixed(3)}</small>
            </div>
        `;
        
        // Create 200km radius circle (but don't add to map yet - only on click/hover)
        const circle = L.circle([lat, lon], {
            radius: 200000, // 200km in meters
            color: '#e74c3c',
            fillColor: '#e74c3c',
            fillOpacity: 0.1,
            weight: 2,
            dashArray: '5, 5'
        });
        
        // Add marker
        const marker = L.marker([lat, lon], { icon })
            .addTo(map)
            .bindPopup(popupContent);
        
        // Show circle on click or hover
        marker.on('click', function() {
            if (!map.hasLayer(circle)) {
                circle.addTo(map);
            }
        });
        
        marker.on('mouseover', function() {
            if (!map.hasLayer(circle)) {
                circle.addTo(map);
            }
        });
        
        marker.on('mouseout', function() {
            // Keep circle visible on click, only hide on mouseout if not clicked
            // We'll track if it was clicked
            if (!marker._clicked) {
                if (map.hasLayer(circle)) {
                    map.removeLayer(circle);
                }
            }
        });
        
        // Track click state
        marker.on('click', function() {
            marker._clicked = true;
        });
        
        // Hide circle when popup closes
        marker.on('popupclose', function() {
            marker._clicked = false;
            if (map.hasLayer(circle)) {
                map.removeLayer(circle);
            }
        });
        
        console.log(`Added earthquake marker at [${lat}, ${lon}] with magnitude ${mag}`);
        
        // Store in a separate object for earthquakes
        if (!markers.earthquakes) {
            markers.earthquakes = [];
        }
        markers.earthquakes.push(marker);
        
        // Store circles separately for cleanup
        if (!markers.earthquakeCircles) {
            markers.earthquakeCircles = [];
        }
        markers.earthquakeCircles.push(circle);
    });
    
    console.log(`Total earthquake markers added: ${markers.earthquakes ? markers.earthquakes.length : 0}`);
}

async function renderDashboard(date = null) {
    console.log('renderDashboard called with date:', date);
    // The template already has the structure, we just need to update it
    // Show loading state
    const mapContainer = document.getElementById('map-container');
    if (mapContainer) {
        mapContainer.innerHTML = '<div style="display: flex; align-items: center; justify-content: center; height: 100%; color: #ecf0f1;"><p>Loading map data...</p></div>';
    }
    
    let data;
    try {
        console.log('Loading data...');
        data = await loadData(date);
        console.log('Data loaded:', data ? 'Success' : 'Failed', data);
        
        if (!data) {
            const dateStr = date || selectedDate || 'selected date';
            console.warn('No data available for date:', dateStr);
            if (mapContainer) {
                mapContainer.innerHTML = `
                    <div class="no-data" style="text-align: center; padding: 40px; color: #ecf0f1;">
                        <h2 style="color: #e74c3c; margin-bottom: 20px;">⚠️ No Data Available</h2>
                        <p style="font-size: 1.1em; margin-bottom: 10px;">
                            No data is available for <strong>${dateStr}</strong> or any previous days (within 7 days).
                        </p>
                        <p style="color: #95a5a6; font-size: 0.9em;">
                            Please select a different date from the dropdown above.
                        </p>
                    </div>
                `;
            }
            return;
        }
    } catch (error) {
        console.error('Error in renderDashboard:', error);
        if (mapContainer) {
            mapContainer.innerHTML = `
                <div class="error" style="text-align: center; padding: 40px; color: #e74c3c;">
                    <h2 style="margin-bottom: 20px;">❌ Error Loading Data</h2>
                    <p style="font-size: 1.1em; margin-bottom: 10px;">
                        ${error.message || 'Unknown error occurred'}
                    </p>
                    <p style="color: #95a5a6; font-size: 0.9em;">
                        Please check the browser console for details.
                    </p>
                </div>
            `;
        }
        return;
    }
    
    // Data was successfully loaded - continue with rendering
    // Remove any existing fallback notices first to prevent duplicates
    const existingNotices = document.querySelectorAll('.fallback-notice');
    existingNotices.forEach(notice => notice.remove());
    
    // Show notice if any stations are using fallback data
    if (data.station_dates) {
        const stationsUsingFallback = Object.entries(data.station_dates)
            .filter(([station, dateUsed]) => dateUsed !== data.selected_date)
            .map(([station, dateUsed]) => ({ station, dateUsed }));
        
        const stationsWithSelectedDate = Object.entries(data.station_dates)
            .filter(([station, dateUsed]) => dateUsed === data.selected_date)
            .map(([station]) => station);
        
        // Group fallback stations by the date they're using
        const fallbackByDate = {};
        stationsUsingFallback.forEach(({ station, dateUsed }) => {
            if (!fallbackByDate[dateUsed]) {
                fallbackByDate[dateUsed] = [];
            }
            fallbackByDate[dateUsed].push(station);
        });
        
        if (stationsUsingFallback.length > 0) {
            const notice = document.createElement('div');
            notice.className = 'fallback-notice';
            notice.style.cssText = 'background: rgba(243, 156, 18, 0.15); border-left: 4px solid #f39c12; padding: 16px 20px; margin: 15px 0; border-radius: 8px; color: #ecf0f1; font-size: 0.95rem;';
            
            let noticeHTML = `<div style="display: flex; align-items: flex-start; gap: 12px;">`;
            noticeHTML += `<div style="font-size: 1.5em;">ℹ️</div>`;
            noticeHTML += `<div style="flex: 1;">`;
            noticeHTML += `<strong style="color: #f39c12; display: block; margin-bottom: 8px;">Data Availability Notice</strong>`;
            noticeHTML += `<p style="margin: 8px 0;">`;
            noticeHTML += `<strong>${stationsWithSelectedDate.length}</strong> station(s) have data for <strong>${formatDateForSelector(data.selected_date)}</strong>. `;
            noticeHTML += `<strong>${stationsUsingFallback.length}</strong> station(s) are using previous day's data:`;
            noticeHTML += `</p>`;
            
            // List stations by fallback date
            Object.entries(fallbackByDate).forEach(([fallbackDate, stations]) => {
                const stationList = stations.length <= 8 
                    ? stations.join(', ')
                    : `${stations.slice(0, 8).join(', ')} and ${stations.length - 8} more`;
                noticeHTML += `<div style="margin: 8px 0; padding-left: 16px; border-left: 2px solid rgba(243, 156, 18, 0.5);">`;
                noticeHTML += `<strong>${stations.length} station(s)</strong> using data from <strong>${formatDateForSelector(fallbackDate)}</strong>: `;
                noticeHTML += `<span style="color: #bdc3c7; font-size: 0.9em;">${stationList}</span>`;
                noticeHTML += `</div>`;
            });
            
            if (data.selected_date === new Date().toISOString().split('T')[0]) {
                noticeHTML += `<p style="margin-top: 12px; font-size: 0.9em; color: #bdc3c7; font-style: italic;">`;
                noticeHTML += `Note: This is normal if the nighttime window (20:00-04:00 local time) has not yet completed for these stations.`;
                noticeHTML += `</p>`;
            } else {
                noticeHTML += `<p style="margin-top: 12px; font-size: 0.9em; color: #bdc3c7; font-style: italic;">`;
                noticeHTML += `Note: EVT threshold calculation requires 7 days of data. Stations without data for the selected date are showing the most recent available data.`;
                noticeHTML += `</p>`;
            }
            
            noticeHTML += `</div></div>`;
            notice.innerHTML = noticeHTML;
            
            const container = document.querySelector('.container') || document.body;
            const mapSection = document.querySelector('.map-section');
            if (mapSection && mapSection.parentNode) {
                mapSection.parentNode.insertBefore(notice, mapSection);
            } else {
                container.insertBefore(notice, container.firstChild);
            }
        }
    }
    
    // Update date selector
    const dateSelector = document.getElementById('date-selector');
    if (dateSelector && data.available_dates) {
        dateSelector.innerHTML = '';
        data.available_dates.forEach(date => {
            const option = document.createElement('option');
            option.value = date;
            option.textContent = formatDateForSelector(date);
            if (date === data.selected_date || date === data.most_recent_date) {
                option.selected = true;
            }
            dateSelector.appendChild(option);
        });
    }
    
    // Load metadata - handle both array and object formats
    if (data.metadata) {
        if (Array.isArray(data.metadata)) {
            // Format: metadata is an array of objects with 'code' field
            data.metadata.forEach(station => {
                if (station.code) {
                    stationMetadata[station.code] = station;
                }
            });
        } else if (typeof data.metadata === 'object') {
            // Format: metadata is an object with station codes as keys
            Object.keys(data.metadata).forEach(code => {
                stationMetadata[code] = data.metadata[code];
            });
        }
    }
    
    allStations = data.stations || [];
    allStationsData = data.data || {};
    
    // Identify anomalous stations
    anomalousStations = [];
    let totalStations = 0;
    let anomalousCount = 0;
    let withEQ = 0;
    
    // For cumulative false positives/negatives since Nov 18, 2025
    const ANALYSIS_START_DATE = '2025-11-18';
    let allFalsePositives = []; // Array of {station, date, ...}
    let allFalseNegatives = []; // Array of {station, date, earthquake_time, ...}
    
    const stationDataMap = {};
    for (const station of allStations) {
        totalStations++;
        const stationData = allStationsData[station];
        const hasAnomaly = stationData && stationData.is_anomalous;
        
        if (hasAnomaly) {
            anomalousCount++;
            anomalousStations.push(station);
            // Load correlations for the selected date
            const eqCorrelations = await loadEarthquakeCorrelations(station, data.selected_date);
            // Filter by magnitude >= 5.0 for reliability
            const reliableCorrelations = eqCorrelations.filter(eq => parseFloat(eq.earthquake_magnitude || eq.magnitude || 0) >= 5.0);
            if (reliableCorrelations.length > 0) {
                withEQ++;
            } else {
                // This is a false positive for the selected date
                allFalsePositives.push({
                    station: station,
                    date: data.selected_date,
                    stationData: stationData
                });
            }
            stationDataMap[station] = { stationData, eqCorrelations: reliableCorrelations };
        } else {
            // Check for false negatives (EQ >= 5.0 occurred but no anomaly) for the selected date
            const fn = await loadFalseNegatives(station, data.selected_date);
            if (fn.length > 0) {
                fn.forEach(fnItem => {
                    allFalseNegatives.push({
                        station: station,
                        date: data.selected_date,
                        earthquake_time: fnItem.earthquake_time || fnItem.time,
                        ...fnItem
                    });
                });
            }
            stationDataMap[station] = { stationData: null, eqCorrelations: [], falseNegatives: fn };
        }
    }
    
    // Load cumulative false positives and false negatives from all dates since analysis start
    const datesSinceStart = (data.available_dates || []).filter(d => d >= ANALYSIS_START_DATE).sort();
    
    // Load false positives and false negatives from all dates
    for (const date of datesSinceStart) {
        for (const station of allStations) {
            // Load station data for this date to check for false positives
            try {
                const stationResponse = await fetch(`data/${station}_${date}.json`);
                if (stationResponse.ok) {
                    const stationDataForDate = await stationResponse.json();
                    if (stationDataForDate.is_anomalous) {
                        // Check if it's a false positive (anomaly without earthquake)
                        const eqCorrelations = await loadEarthquakeCorrelations(station, date);
                        const reliableCorrelations = eqCorrelations.filter(eq => parseFloat(eq.earthquake_magnitude || eq.magnitude || 0) >= 5.0);
                        if (reliableCorrelations.length === 0) {
                            // False positive - check if we already have it
                            const exists = allFalsePositives.some(fp => fp.station === station && fp.date === date);
                            if (!exists) {
                                allFalsePositives.push({
                                    station: station,
                                    date: date,
                                    stationData: stationDataForDate
                                });
                            }
                        }
                    } else {
                        // Check for false negatives
                        const fn = await loadFalseNegatives(station, date);
                        if (fn.length > 0) {
                            fn.forEach(fnItem => {
                                // Check if we already have this false negative
                                const eqTime = fnItem.earthquake_time || fnItem.time;
                                const exists = allFalseNegatives.some(fn => 
                                    fn.station === station && 
                                    fn.earthquake_time === eqTime
                                );
                                if (!exists) {
                                    allFalseNegatives.push({
                                        station: station,
                                        date: date,
                                        earthquake_time: eqTime,
                                        ...fnItem
                                    });
                                }
                            });
                        }
                    }
                }
            } catch (error) {
                // Skip if file doesn't exist
                continue;
            }
        }
    }
    
    // Calculate totals and find latest occurrences
    const falseAlarms = allFalsePositives.length;
    const falseNegatives = allFalseNegatives.length;
    
    // Find latest false positive date
    let latestFalsePositiveDate = null;
    if (allFalsePositives.length > 0) {
        const dates = allFalsePositives.map(fp => fp.date).sort().reverse();
        latestFalsePositiveDate = dates[0];
    }
    
    // Find latest false negative earthquake time
    let latestFalseNegativeDate = null;
    if (allFalseNegatives.length > 0) {
        const dates = allFalseNegatives
            .map(fn => {
                const eqTime = fn.earthquake_time || fn.time;
                if (typeof eqTime === 'string') {
                    return eqTime.split('T')[0]; // Extract date part
                }
                return fn.date;
            })
            .filter(d => d)
            .sort()
            .reverse();
        latestFalseNegativeDate = dates[0];
    }
    
    // Load earthquake statistics for selected date only (no fallback)
    let eqStats = { global: 0, within200km: 0 };
    let eqDateUsed = data.selected_date;
    
    // Only try the selected date
    try {
        const statsResponse = await fetch(`data/earthquake_stats_${data.selected_date}.json`);
        if (statsResponse.ok) {
            const statsData = await statsResponse.json();
            eqStats = {
                global: statsData.global_count || statsData.global || 0,
                within200km: statsData.within_200km_count || statsData.within200km || 0
            };
            eqDateUsed = data.selected_date;
        }
    } catch (error) {
        console.debug('Could not load earthquake statistics for selected date:', error);
    }
    
    // Create summary stats boxes (like before, but better styled)
    const summaryStatsEl = document.getElementById('summary-stats');
    if (summaryStatsEl) {
        summaryStatsEl.innerHTML = `
            <div class="metric-card">
                <h3>Active Stations</h3>
                <div class="value">${totalStations}</div>
                <div class="label">Total stations monitored</div>
            </div>
            <div class="metric-card">
                <h3>Anomalies Detected</h3>
                <div class="value">${anomalousCount}</div>
                <div class="label">Polarization ratio anomalies</div>
            </div>
            <div class="metric-card">
                <h3>Events (24h)</h3>
                <div class="value">${eqStats.global}</div>
                <div class="label">🌍 Global M≥5.0</div>
                <div class="sub-label" style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
                    ${eqStats.within200km} within 200km of stations
                </div>
            </div>
            <div class="metric-card ${falseAlarms > 0 ? 'warning' : ''}">
                <h3>False Positives</h3>
                <div class="value">${falseAlarms}</div>
                <div class="label">Anomalies without EQ M≥5.0</div>
                <div class="sub-label" style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
                    Since: ${formatDateForSelector(ANALYSIS_START_DATE)}${latestFalsePositiveDate ? `<br>Latest: ${formatDateForSelector(latestFalsePositiveDate)}` : ''}
                </div>
            </div>
            <div class="metric-card ${falseNegatives > 0 ? 'warning' : ''}">
                <h3>False Negatives</h3>
                <div class="value">${falseNegatives}</div>
                <div class="label">EQ M≥5.0 without anomaly</div>
                <div class="sub-label" style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
                    Since: ${formatDateForSelector(ANALYSIS_START_DATE)}${latestFalseNegativeDate ? `<br>Latest: ${formatDateForSelector(latestFalseNegativeDate)}` : ''}
                </div>
            </div>
        `;
    }
    
    // Update timestamp will be handled in renderDashboard
    
    // Update station selector dropdown
    const stationSelector = document.getElementById('station-selector');
    if (stationSelector) {
        stationSelector.innerHTML = '<option value="">Select a station...</option>';
        
        // Add anomalous stations first
        anomalousStations.forEach(station => {
            const metadata = stationMetadata[station] || {};
            const stationData = allStationsData[station];
            const eqCorrelations = stationDataMap[station]?.eqCorrelations || [];
            const hasEQ = eqCorrelations.length > 0;
            const label = `${station} - ${metadata.name || station}${hasEQ ? ' 🌋' : ' ⚠️'}`;
            const option = document.createElement('option');
            option.value = station;
            option.textContent = label;
            if (anomalousStations.indexOf(station) === 0) {
                option.selected = true;
            }
            stationSelector.appendChild(option);
        });
        
        // Add other stations
        allStations.filter(s => !anomalousStations.includes(s)).forEach(station => {
            const metadata = stationMetadata[station] || {};
            const option = document.createElement('option');
            option.value = station;
            option.textContent = `${station} - ${metadata.name || station} (Normal)`;
            stationSelector.appendChild(option);
        });
        
        // Setup change handler if not already set
        if (!stationSelector.hasAttribute('data-handler-attached')) {
            stationSelector.setAttribute('data-handler-attached', 'true');
            stationSelector.addEventListener('change', async (e) => {
                const selectedStation = e.target.value;
                if (selectedStation) {
                    await renderStationPlot(selectedStation);
                } else {
                    const plotDiv = document.getElementById('selected-station-plot');
                    if (plotDiv) plotDiv.innerHTML = '';
                }
            });
        }
        
        // Load first anomalous station by default
        if (anomalousStations.length > 0 && !stationSelector.value) {
            stationSelector.value = anomalousStations[0];
            await renderStationPlot(anomalousStations[0]);
        }
    }
    
    // Initialize map - wait a bit for DOM to be ready
    setTimeout(async () => {
        const mapEl = document.getElementById('map-container');
        if (!mapEl) {
            console.error('Map container not found');
            return;
        }
        
        // Clear any loading message
        mapEl.innerHTML = '';
        
        // Ensure container has dimensions
        if (mapEl.offsetHeight === 0) {
            console.warn('Map container has no height, setting minimum height');
            mapEl.style.minHeight = '600px';
        }
        
        try {
            console.log('Initializing map...');
            initMap();
            
            if (!map) {
                console.error('Map initialization failed');
                mapEl.innerHTML = '<div style="padding: 20px; color: #e74c3c;">Failed to initialize map</div>';
                return;
            }
            
            // Wait for map to be ready
            await new Promise(resolve => setTimeout(resolve, 500));
            
            console.log('Adding station markers...', allStations.length);
            // Add all station markers
            for (const station of allStations) {
                const { stationData, eqCorrelations } = stationDataMap[station] || { stationData: allStationsData[station], eqCorrelations: [] };
                addStationToMap(station, stationData, eqCorrelations, data);
            }
            
            console.log('Loading earthquakes...');
            // Add earthquake markers
            const recentEarthquakes = await loadRecentEarthquakes(data.selected_date);
            console.log('Loaded earthquakes for map:', recentEarthquakes.length, recentEarthquakes);
            addEarthquakeMarkers(recentEarthquakes);
            
            // Invalidate map size to ensure it renders correctly
            setTimeout(() => {
                if (map) {
                    map.invalidateSize();
                    console.log('Map size invalidated');
                }
            }, 100);
        } catch (error) {
            console.error('Error initializing map:', error);
            mapEl.innerHTML = `<div style="padding: 20px; color: #e74c3c;">Error loading map: ${error.message}<br><small>${error.stack}</small></div>`;
        }
    }, 500);
    
    // Setup mobile plot panel toggle
    const togglePlotBtn = document.getElementById('toggle-plot-panel');
    const plotPanelContent = document.getElementById('plot-panel-content');
    if (togglePlotBtn && plotPanelContent) {
        // On mobile, start collapsed (but allow user to expand)
        const isMobile = window.innerWidth <= 768;
        if (isMobile) {
            // Set initial collapsed state
            plotPanelContent.style.maxHeight = '0';
            plotPanelContent.style.opacity = '0';
            plotPanelContent.style.overflow = 'hidden';
            togglePlotBtn.textContent = '▲';
        }
        
        togglePlotBtn.addEventListener('click', () => {
            const isCollapsed = plotPanelContent.style.maxHeight === '0px' || 
                               plotPanelContent.classList.contains('collapsed');
            
            if (isCollapsed) {
                // Expand
                plotPanelContent.style.maxHeight = plotPanelContent.scrollHeight + 'px';
                plotPanelContent.style.opacity = '1';
                plotPanelContent.classList.remove('collapsed');
                togglePlotBtn.textContent = '▼';
            } else {
                // Collapse
                plotPanelContent.style.maxHeight = '0';
                plotPanelContent.style.opacity = '0';
                plotPanelContent.classList.add('collapsed');
                togglePlotBtn.textContent = '▲';
            }
        });
        
        // Handle window resize
        let resizeTimer;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => {
                const isMobileNow = window.innerWidth <= 768;
                if (!isMobileNow) {
                    // Desktop: always show
                    plotPanelContent.style.maxHeight = 'none';
                    plotPanelContent.style.opacity = '1';
                    plotPanelContent.classList.remove('collapsed');
                }
            }, 250);
        });
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
    
    // Update timestamp (UTC-based)
    const timestampEl = document.getElementById('timestamp');
    if (timestampEl) {
        if (data.last_updated) {
            timestampEl.textContent = new Date(data.last_updated).toLocaleString('en-US', {
                timeZone: 'UTC',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                timeZoneName: 'short'
            });
        } else {
            // Fallback to current time in UTC
            timestampEl.textContent = new Date().toLocaleString('en-US', {
                timeZone: 'UTC',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                timeZoneName: 'short'
            });
        }
    }
}

async function renderStationPlot(stationCode) {
    const plotDiv = document.getElementById('selected-station-plot');
    if (!plotDiv) return;
    
    plotDiv.innerHTML = '<div class="loading">Loading station data...</div>';
    
    const stationData = allStationsData[stationCode];
    const metadata = stationMetadata[stationCode] || {};
    const eqCorrelations = await loadEarthquakeCorrelations(stationCode, selectedDate);
        // Filter by magnitude >= 5.0 for reliability
        const reliableCorrelations = eqCorrelations.filter(eq => parseFloat(eq.earthquake_magnitude || eq.magnitude || 0) >= 5.0);
    const hasEQ = reliableCorrelations.length > 0;
    const hasAnomaly = stationData && stationData.is_anomalous;
    const falseNegatives = await loadFalseNegatives(stationCode, selectedDate);
    
    // Get the date being used for this station
    const stationDateUsed = stationData?.date || selectedDate || mostRecentDate;
    const isUsingFallback = selectedDate && stationDateUsed !== selectedDate;
    
    let html = `<div class="station-plot-card">`;
    html += `<div class="plot-header">`;
    html += `<h3>${stationCode} - ${metadata.name || stationCode}</h3>`;
    html += `<p class="plot-location">${metadata.country || ''} | 📍 ${metadata.latitude ? metadata.latitude.toFixed(3) : 'N/A'}, ${metadata.longitude ? metadata.longitude.toFixed(3) : 'N/A'}</p>`;
    
    // Show date indicator
    if (isUsingFallback && selectedDate) {
        html += `<div style="margin-top: 8px; padding: 8px 12px; background: rgba(243, 156, 18, 0.15); border-left: 3px solid #f39c12; border-radius: 4px; font-size: 0.9em; color: #f39c12;">`;
        html += `📅 Showing data from <strong>${formatDate(stationDateUsed)}</strong> (selected: ${formatDateForSelector(selectedDate)})`;
        html += `</div>`;
    } else if (stationData) {
        html += `<div style="margin-top: 8px; padding: 8px 12px; background: rgba(149, 165, 166, 0.1); border-left: 3px solid #95a5a6; border-radius: 4px; font-size: 0.9em; color: #95a5a6;">`;
        html += `📅 Data from: <strong>${formatDate(stationDateUsed)}</strong>`;
        html += `</div>`;
    }
    
    if (hasAnomaly) {
        html += `<div class="plot-status ${hasEQ ? 'status-eq' : 'status-false'}">`;
        html += hasEQ ? `🌋 EQ Correlation Found (M≥5.0): ${reliableCorrelations.length}` : `⚠️ False Alarm (No EQ M≥5.0)`;
        html += `</div>`;
    } else {
        html += `<div class="plot-status status-normal">✅ Normal</div>`;
        if (falseNegatives.length > 0) {
            html += `<div class="plot-status status-false-negative" style="margin-top: 8px;">❌ False Negative: ${falseNegatives.length} EQ M≥5.0 without anomaly</div>`;
        }
    }
    html += `</div>`;
    
    // Load and display figure
    // Use the date from stationData (which should match selectedDate)
    // This ensures the figure matches the data being displayed
    const plotDate = stationData?.date || selectedDate || mostRecentDate;
    console.log(`[renderStationPlot] Loading figure for ${stationCode} with date: ${plotDate} (stationData.date: ${stationData?.date}, selectedDate: ${selectedDate})`);
    const figures = await loadStationFigures(stationCode, plotDate);
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
        html += `<div class="info-row"><span class="info-label">Threshold:</span><span class="info-value">${parseFloat(stationData.threshold || 0).toFixed(2)}</span> <span style="font-size: 0.8em; color: var(--text-secondary);">(EVT GPD, 7-day)</span></div>`;
        html += `<div class="info-row"><span class="info-label">Anomaly Hours:</span><span class="info-value">${stationData.nAnomHours || 0}</span></div>`;
        // Show reliable correlations (M>=5.0)
        if (hasEQ && reliableCorrelations.length > 0) {
            html += `<div class="eq-info">`;
            html += `<h4>🌋 Earthquake Correlations (M≥5.0):</h4>`;
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
            html += `<h4>❌ False Negatives (M≥5.0, no anomaly detected):</h4>`;
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

async function loadStationFigures(station, date = null) {
    // If date is provided, use it directly
    if (date) {
        const dateStr = date.replace(/-/g, '');
        const filename = `PRA_${station}_${dateStr}.png`;
        console.log(`[loadStationFigures] Using provided date for ${station}: ${date} -> ${filename}`);
        return [filename];
    }
    
    // Fallback: Try to get date from station data
    try {
        // Try to use selectedDate or mostRecentDate
        const useDate = selectedDate || mostRecentDate;
        if (useDate) {
            const dateStr = useDate.replace(/-/g, '');
            const filename = `PRA_${station}_${dateStr}.png`;
            console.log(`[loadStationFigures] Using selectedDate/mostRecentDate for ${station}: ${useDate} -> ${filename}`);
            return [filename];
        }
        
        // Last resort: Try to fetch from date-specific JSON file
        // Check available dates and try the most recent one
        if (availableDates && availableDates.length > 0) {
            console.log(`[loadStationFigures] Trying available dates for ${station}:`, availableDates);
            for (const availableDate of availableDates) {
                const dateStr = availableDate.replace(/-/g, '');
                const filename = `PRA_${station}_${dateStr}.png`;
                // Check if file exists by trying to load it
                try {
                    const testResponse = await fetch(`figures/${station}/${filename}`, { method: 'HEAD' });
                    if (testResponse.ok) {
                        console.log(`[loadStationFigures] Found plot file for ${station}: ${filename}`);
                        return [filename];
                    }
                } catch (e) {
                    // Continue to next date
                }
            }
        }
    } catch (e) {
        console.warn(`[loadStationFigures] Could not determine figure for station ${station}:`, e);
    }
    
    console.warn(`[loadStationFigures] No plot file found for station ${station}`);
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
        const eqCorrelations = await loadEarthquakeCorrelations(station, selectedDate);
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


// Download anomalies CSV
async function downloadAnomaliesCSV() {
    try {
        // Collect all anomaly data from all stations using JSON data we already have
        const allAnomalies = [];
        
        // Use the data we already loaded in allStationsData
        for (const station of allStations) {
            try {
                const stationData = allStationsData[station];
                if (stationData && stationData.timestamps && stationData.isAnomalous) {
                    // Extract anomalies from the station data
                    for (let i = 0; i < stationData.timestamps.length; i++) {
                        if (stationData.isAnomalous[i]) {
                            const anomaly = {
                                Station: station,
                                TimeOfAnomaly: stationData.timestamps[i],
                                AnomalyValue: stationData.P ? stationData.P[i] : '',
                                nZ: stationData.nZ ? stationData.nZ[i] : '',
                                nG: stationData.nG ? stationData.nG[i] : '',
                                Threshold: stationData.threshold || ''
                            };
                            allAnomalies.push(anomaly);
                        }
                    }
                } else {
                    // Fallback: try to load from CSV if JSON doesn't have anomaly info
                    try {
                        const response = await fetch(`data/${station}_anomalies.csv`);
                        if (response.ok) {
                            const csvText = await response.text();
                            const anomalies = parseCSV(csvText);
                            
                            // Add station code to each anomaly
                            anomalies.forEach(anomaly => {
                                anomaly.Station = station;
                                allAnomalies.push(anomaly);
                            });
                        }
                    } catch (error) {
                        // Silently ignore - CSV files are optional
                    }
                }
            } catch (error) {
                // Silently ignore errors for individual stations
            }
        }
        
        if (allAnomalies.length === 0) {
            alert('No anomalies found to download.');
            return;
        }
        
        // Convert to CSV format
        const headers = Object.keys(allAnomalies[0]);
        const csvRows = [
            headers.join(','),
            ...allAnomalies.map(row => 
                headers.map(header => {
                    const value = row[header] || '';
                    // Escape commas and quotes in CSV
                    if (typeof value === 'string' && (value.includes(',') || value.includes('"'))) {
                        return `"${value.replace(/"/g, '""')}"`;
                    }
                    return value;
                }).join(',')
            )
        ];
        
        const csvContent = csvRows.join('\n');
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        
        link.setAttribute('href', url);
        link.setAttribute('download', `anomalies_${selectedDate || new Date().toISOString().split('T')[0]}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        console.log(`Downloaded ${allAnomalies.length} anomalies`);
    } catch (error) {
        console.error('Error downloading anomalies CSV:', error);
        alert('Error downloading anomalies CSV. Please try again.');
    }
}
