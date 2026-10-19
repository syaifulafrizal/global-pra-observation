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
let isAggregatedDataLoaded = false;
let stationCharts = [];
let dashboardGeneration = 0;
let stationPlotGeneration = 0;
let displayedDate = null;
let displayedSnapshotSignature = null;
const dataRequests = new Map();
const DATA_CACHE_LIMIT = 32;
let requestEpoch = 0;

function invalidateDataRequests() {
    requestEpoch++;
    dataRequests.clear();
}

async function cachedData(url, kind = 'json') {
    const existing = dataRequests.get(url);
    if (existing) {
        dataRequests.delete(url); dataRequests.set(url, existing);
        return existing;
    }
    const epoch = requestEpoch;
    const pending = (async () => {
        const response = await fetch(url, {cache: 'no-cache'});
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${url}`);
        return kind === 'text' ? response.text() : response.json();
    })();
    dataRequests.set(url, pending);
    while (dataRequests.size > DATA_CACHE_LIMIT) dataRequests.delete(dataRequests.keys().next().value);
    try { return await pending; }
    catch (error) {
        if (epoch === requestEpoch && dataRequests.get(url) === pending) dataRequests.delete(url);
        throw error;
    }
}

async function parallelMap(values, operation, limit = 3) {
    const results = new Array(values.length);
    let next = 0;
    await Promise.all(Array.from({length: Math.min(limit, values.length)}, async () => {
        while (next < values.length) {
            const index = next++;
            results[index] = await operation(values[index]);
        }
    }));
    return results;
}


// Initialize
document.addEventListener('DOMContentLoaded', () => {
    if (typeof Chart !== 'undefined') {
        Chart.defaults.font.family = 'DM Sans, sans-serif';
        Chart.defaults.font.size = 10;
        Chart.defaults.animation = false;
    }
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
            refreshChartTheme();
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
        renderDashboard(currentDate, {refresh: true});
    }, 300000); // Auto-refresh every 5 minutes
});

async function loadData(date = null, isCurrent = () => true) {
    try {
        // First, load stations.json to get available dates
        const metadata = await cachedData(DATA_URL);
        if (!isCurrent()) return null;

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

        // OPTIMIZATION: Load aggregated data file for the selected date
        // This replaces 100+ individual station requests with a single request
        console.log(`Loading aggregated data for ${date}...`);
        const aggregatedUrl = `data/aggregated_${date}.json`;

        try {
            {
                const aggregatedData = await cachedData(aggregatedUrl);
                if (!isCurrent()) return null;
                console.log(`✓ Loaded aggregated data for ${date} (${Object.keys(aggregatedData.stations || {}).length} stations)`);
                isAggregatedDataLoaded = true;

                // Transform aggregated data to match expected format
                const dateData = aggregatedData.stations || {};
                const stationDates = {};

                // Track which date each station is using (all using same date from aggregated file)
                for (const station of Object.keys(dateData)) {
                    stationDates[station] = dateData[station]?.date || aggregatedData.date || date;
                }

                // Store earthquake correlations and false negatives for later use
                window.earthquakeCorrelations = aggregatedData.earthquake_correlations || {};
                window.falseNegatives = aggregatedData.false_negatives || {};

                return {
                    stations: metadata.stations || Object.keys(dateData),
                    data: dateData,
                    metadata: aggregatedData.metadata || metadata.metadata || {},
                    available_dates: availableDates,
                    most_recent_date: mostRecentDate,
                    selected_date: date,
                    station_dates: stationDates,
                    station_quality: aggregatedData.station_quality || {},
                    is_hybrid_aggregation: aggregatedData.is_hybrid_aggregation || Object.values(stationDates).some(day => day !== date),
                    last_updated: metadata.last_updated || aggregatedData.generated_at
                };
            }
        } catch (error) {
            if (!isCurrent()) return null;
            console.warn(`Error loading aggregated data for ${date}:`, error);
            isAggregatedDataLoaded = false;
            // Fall back to old method on error
            return await loadDataFallback(date, metadata, availableDates, mostRecentDate, isCurrent);
        }
    } catch (error) {
        console.error('Error loading data:', error);
        return null;
    }
}

// Fallback function for loading individual station files (kept for compatibility)
function stationResultUsable(data) {
    const powers = data?.P;
    if (data?.data_quality?.status === 'invalid' || !Array.isArray(powers) || !powers.length ||
        !powers.every(value => value !== null && value !== '' && Number.isFinite(Number(value)))) return false;
    const vertical = data.nZ || [], horizontal = data.nG || [];
    const close = (a, b) => Math.abs(Number(a) - Number(b)) <= 1e-12 * Math.max(Math.abs(a), Math.abs(b));
    return !(vertical.length === powers.length && horizontal.length === powers.length &&
        powers.every(value => Math.abs(Number(value) - 0.5) <= 1e-12) &&
        vertical.every(value => close(value, vertical[0])) && horizontal.every((value, i) => close(value, 2 * vertical[i])));
}

async function loadDataFallback(date, metadata, availableDates, mostRecentDate, isCurrent = () => true) {
    console.log('Using fallback method: loading individual station files...');
    window.earthquakeCorrelations = {};
    window.falseNegatives = {};

    const dateData = {};
    const stationDates = {};
    const stationQuality = {};
    let hasAnyData = false;
    const previous = new Date(new Date(`${date}T00:00:00Z`).getTime() - 86400000).toISOString().slice(0, 10);

    // Match the aggregate's one-previous-night fallback and actual-date provenance.
    await parallelMap(metadata.stations || [], async station => {
        if (!isCurrent()) return null;
        stationQuality[station] = 'missing';
        for (const day of [date, previous]) {
            try {
                const stationResponse = await fetch(`data/${station}_${day}.json`, { cache: 'no-cache' });
                if (!stationResponse.ok) continue;
                const stationData = await stationResponse.json();
                if (!isCurrent()) return null;
                if (stationData.date !== day || !stationResultUsable(stationData)) {
                    stationQuality[station] = 'invalid';
                    break;
                }
                dateData[station] = stationData;
                stationDates[station] = day;
                stationQuality[station] = stationData.data_quality?.status || 'historical';
                hasAnyData = true;
                break;
            } catch (error) {
                console.debug(`Station ${station}: No data for ${day}`);
            }
        }
    });
    if (!isCurrent()) return null;

    if (!hasAnyData) {
        return null;
    }

    return {
        stations: metadata.stations || [],
        data: dateData,
        metadata: metadata.metadata || [],
        available_dates: availableDates,
        most_recent_date: mostRecentDate,
        selected_date: date,
        station_dates: stationDates,
        station_quality: stationQuality,
        is_hybrid_aggregation: Object.values(stationDates).some(day => day !== date),
        last_updated: metadata.last_updated
    };
}

function isConfirmedCorrelation(event) {
    return event?.status === 'TP' && Number(event.earthquake_magnitude || event.magnitude) >= 5;
}

function isCorrelationVisible(event) {
    return isConfirmedCorrelation(event) || ['FP', 'Pending', 'Unknown'].includes(event?.status);
}

function isConfirmedFalsePositive(entry) {
    return entry?.status === 'FP' && entry.has_correlated_eq !== true;
}

async function loadEarthquakeCorrelations(station, date = null) {
    // OPTIMIZATION: Use cached data from aggregated file if available
    if (window.earthquakeCorrelations && window.earthquakeCorrelations[station]) {
        const correlations = window.earthquakeCorrelations[station];
        // Filter by magnitude >= 5.0 for reliability
        return correlations.filter(isCorrelationVisible);
    }

    // If we loaded aggregated data successfully but found no correlations for this station,
    // assume there are none (don't make 404 requests)
    if (isAggregatedDataLoaded) {
        return [];
    }

    // Fallback: Load from individual CSV file
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
                    return correlations.filter(isCorrelationVisible);
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
        return correlations.filter(isCorrelationVisible).filter(eq => !date || String(eq.anomaly_date || '').slice(0, 10) === date);
    } catch (error) {
        // Silently return empty array - CSV files are optional
        return [];
    }
}

async function loadFalseNegatives(station, date = null) {
    // OPTIMIZATION: Use cached data from aggregated file if available
    if (window.falseNegatives && window.falseNegatives[station]) {
        return window.falseNegatives[station];
    }

    // If we loaded aggregated data successfully but found no false negatives for this station,
    // assume there are none (don't make 404 requests)
    if (isAggregatedDataLoaded) {
        return [];
    }

    // Fallback: Load from individual CSV file
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
        return parseCSV(await cachedData(`data/recent_earthquakes_${date}.csv`, 'text'));
    } catch (error) {
        // Return empty array if file doesn't exist
    }

    return [];
}

function parseCSV(csvText) {
    // Preserve quoted place names, commas, newlines and escaped quotes.
    const rows = [];
    let row = [], field = '', quoted = false;
    for (let i = 0; i < csvText.length; i++) {
        const character = csvText[i];
        if (character === '"') {
            if (quoted && csvText[i + 1] === '"') { field += '"'; i++; }
            else quoted = !quoted;
        } else if (character === ',' && !quoted) {
            row.push(field.trim()); field = '';
        } else if ((character === '\n' || character === '\r') && !quoted) {
            if (character === '\r' && csvText[i + 1] === '\n') i++;
            row.push(field.trim());
            if (row.some(value => value !== '')) rows.push(row);
            row = []; field = '';
        } else field += character;
    }
    row.push(field.trim());
    if (row.some(value => value !== '')) rows.push(row);
    const headers = rows.shift() || [];
    return rows.map(values => Object.fromEntries(headers.map((header, index) => [header, values[index] || ''])));
}

function formatDate(dateStr) {
    const date = new Date(`${String(dateStr).split(/[T ]/)[0]}T00:00:00Z`);
    if (!Number.isFinite(date.getTime())) return 'Unknown Date';
    return date.toLocaleDateString('en-US', {
        timeZone: 'UTC',
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

function parseUtcTimestamp(value) {
    const stamp = String(value || '').trim().replace(' ', 'T');
    return new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(stamp) ? stamp : `${stamp}Z`);
}

function earthquakeTimes(value, longitude) {
    const date = parseUtcTimestamp(value);
    if (!Number.isFinite(date.getTime())) return null;
    const offset = Math.round(longitude / 15);
    const local = new Date(date.getTime() + offset * 3600000);
    return {
        utc: date.toISOString().slice(0, 19).replace('T', ' ') + ' UTC',
        local: local.toISOString().slice(0, 19).replace('T', ' ') + ` UTC${offset >= 0 ? '+' : ''}${offset}`
    };
}

function validEventCount(value) {
    return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null;
}

function formatDateForSelector(dateStr) {
    if (!dateStr) return 'Unknown Date';

    // Clean date string to ensure YYYY-MM-DD format
    let cleanDateStr = dateStr;
    if (dateStr.includes('T')) {
        cleanDateStr = dateStr.split('T')[0];
    } else if (dateStr.includes(' ')) {
        cleanDateStr = dateStr.split(' ')[0];
    }

    // Add T00:00:00 to force local time parsing (prevent timezone shifts)
    const date = new Date(cleanDateStr + 'T00:00:00');

    // Fallback if parsing failed
    if (isNaN(date.getTime())) {
        return dateStr;
    }

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

async function fetchHistoryFile(filename) {
    try {
        return await cachedData(`data/${filename}`);
    } catch (error) {
        console.debug(`Failed to load ${filename}:`, error);
    }
    return { entries: [] };
}

async function getAnomalyHistory() {
    return await fetchHistoryFile('anomaly_history.json');
}

async function getFalseNegativeHistory() {
    return await fetchHistoryFile('false_negative_history.json');
}

async function populateDateSelectorFromMetadata() {
    try {
        const metadata = await cachedData(DATA_URL);

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
        } catch (e) { }
    }

    try {
        map = L.map('map-container', {
            minZoom: 0,
            zoomSnap: 0.25,
            maxZoom: 10, // Limit maximum zoom
            zoomControl: true
        }).setView([20, 0], 2);
        map.fitBounds([[-57, -178], [78, 178]], { padding: [12, 12], maxZoom: 2 });
        map.on('resize', () => map.fitBounds([[-57, -178], [78, 178]], { padding: [12, 12], maxZoom: 2, animate: false }));

        // Set max bounds to prevent panning too far
        const southWest = L.latLng(-85, -180);
        const northEast = L.latLng(85, 180);
        const bounds = L.latLngBounds(southWest, northEast);
        map.setMaxBounds(bounds);

        // Add OpenStreetMap tiles with earthquake-themed styling
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
            minZoom: 0,
            maxZoom: 10
        }).addTo(map);

        // Define addEarthquakeCircle function
        window.addEarthquakeCircle = function (lat, lng) {
            if (!map) return;
            // Create a dashed red circle with 200km radius centered on station
            const circle = L.circle([lat, lng], {
                color: '#e74c3c',       // Red color
                weight: 2,
                opacity: 0.8,
                fillColor: '#e74c3c',
                fillOpacity: 0.1,
                radius: 200000,         // 200km in meters
                dashArray: '10, 10'     // Dashed line pattern
            }).addTo(map);

            if (!markers.earthquakeCircles) {
                markers.earthquakeCircles = [];
            }
            markers.earthquakeCircles.push(circle);
            return circle;
        };

        // Legend is now outside the map - see createStandaloneLegend() function

        // Clear existing markers and circles
        if (markers.earthquakes) {
            markers.earthquakes.forEach(m => {
                try { m.remove(); } catch (e) { }
            });
        }
        if (markers.earthquakeCircles) {
            markers.earthquakeCircles.forEach(c => {
                try { c.remove(); } catch (e) { }
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
                } catch (e) { }
            }
        });
        markers = {};
    } catch (error) {
        console.error('Error creating map:', error);
    }
}

function clearMapObservations() {
    if (!map) return;
    map.closePopup();
    map.eachLayer(layer => {
        if (layer instanceof L.Marker || layer instanceof L.Circle) map.removeLayer(layer);
    });
    markers = {};
}

function addStationToMap(stationCode, stationData, eqCorrelations, dataContext = null, falseNegatives = []) {
    if (!map) {
        console.warn('Map not initialized, skipping marker for', stationCode);
        return;
    }

    const metadata = stationMetadata[stationCode];
    if (!metadata || !metadata.latitude || !metadata.longitude) {
        console.warn(`Missing metadata for ${stationCode}`);
        return;
    }

    // Determine status
    const hasAnomaly = stationData && stationData.is_anomalous;
    const hasEQ = eqCorrelations && eqCorrelations.length > 0;
    const hasFN = falseNegatives && falseNegatives.length > 0;

    // Earthquake-themed colors
    let color = 'gray'; // No anomaly
    if (hasAnomaly) {
        // Check if we have a True Positive or False Positive
        const isTP = hasEQ && eqCorrelations.some(isConfirmedCorrelation);
        const isFP = hasEQ && eqCorrelations.every(eq => eq.status === 'FP');

        if (isTP) color = 'eq-reliable'; // Orange/Red
        else if (isFP) color = 'eq-false'; // Red (Alarm without EQ)
        // Pending/unknown forecasts retain a neutral marker until evaluated.
    }
    // False Negatives (Missed EQ) will remain 'gray' but show info in popup

    // Create custom icon with earthquake theme (triangle shape for stations)
    const icon = L.divIcon({
        className: 'station-marker',
        html: `<div class="marker-triangle marker-${color}"></div>`,
        iconSize: [18, 18],
        iconAnchor: [9, 16] // Anchor at bottom center of triangle
    });

    // Get the date being used for this station (from stationData or station_dates)
    const stationDateUsed = stationData?.date || (dataContext?.station_dates && dataContext.station_dates[stationCode]) || 'Unknown';
    const isUsingFallback = dataContext?.selected_date && stationDateUsed !== dataContext.selected_date;

    // Create popup content with earthquake info
    let popupContent = `<div style="min-width: 240px; font-family: Arial, sans-serif;"><strong style="color: #c0392b; font-size: 1.1em;">${metadata.name || stationCode} (${stationCode})</strong><br>`;
    popupContent += `<span style="color: #7f8c8d;">${metadata.country || 'Unknown'}</span><br>`;
    popupContent += `<small>📍 ${metadata.latitude ? metadata.latitude.toFixed(3) : 'N/A'}, ${metadata.longitude ? metadata.longitude.toFixed(3) : 'N/A'}</small><br>`;

    // Show data date with fallback indicator
    if (isUsingFallback && dataContext?.selected_date) {
        popupContent += `<hr style="margin: 8px 0; border-color: var(--accent-warning);">`;
        popupContent += `<small style="color: var(--accent-warning);">📅 Data from: ${formatDate(stationDateUsed)}</small><br>`;
        popupContent += `<small style="color: var(--accent-warning); font-style: italic;">(Selected: ${formatDateForSelector(dataContext.selected_date)})</small><br>`;
    } else if (stationData) {
        popupContent += `<hr style="margin: 8px 0; border-color: var(--text-secondary);">`;
        popupContent += `<small style="color: var(--text-secondary);">📅 Data from: ${formatDate(stationDateUsed)}</small><br>`;
    }

    if (hasAnomaly && stationData) {
        popupContent += `<hr style="margin: 8px 0; border-color: #e74c3c;"><strong style="color: #e74c3c;">⚠️ Anomaly Detected</strong><br>`;
        popupContent += `📅 ${formatDate(stationData.date)}<br>`;
        popupContent += `📊 Threshold: ${parseFloat(stationData.threshold || 0).toFixed(2)}<br>`;
        popupContent += `⏱️ Anomaly Hours: ${stationData.nAnomHours || 0}<br>`;

        // Filter by magnitude >= 5.0 for display
        const reliableCorrelations = eqCorrelations.filter(isConfirmedCorrelation);

        if (hasEQ && reliableCorrelations.length > 0) {
            // Check status (TP/FP)
            const status = reliableCorrelations[0].status || 'TP';
            const statusLabel = status === 'TP' ? 'True Positive' : (status === 'FP' ? 'False Positive' : status);
            const statusColor = status === 'TP' ? '#e67e22' : '#e74c3c';

            popupContent += `<hr style="margin: 8px 0; border-color: ${statusColor};"><strong style="color: ${statusColor};">${statusLabel}</strong><br>`;
            popupContent += `<span style="font-size: 0.9em;">Correlation Found (M≥5.0): ${reliableCorrelations.length}</span><br>`;

            reliableCorrelations.slice(0, 3).forEach((eq) => {
                const mag = eq.earthquake_magnitude || 'N/A';
                const dist = parseFloat(eq.earthquake_distance_km || 0).toFixed(1);
                const days = parseFloat(eq.days_after_anomaly ?? -Number(eq.days_before_anomaly || 0)).toFixed(1);
                popupContent += `🔴 M${mag} @ ${dist}km (${days} days after detection)<br>`;
            });
            if (reliableCorrelations.length > 3) {
                popupContent += `... and ${reliableCorrelations.length - 3} more<br>`;
            }
        } else {
            // Anomaly but no EQ -> Check if 14 days passed for FP
            // We can check backend status if available, or infer
            // For now, if no reliable correlations, it's a False Positive or Pending.
            // The backend usually sets 'FP' or 'Pending' in the correlations list even if empty EQ?
            // No, my backend change ADDS an entry for FP/Pending. So 'reliableCorrelations' should handle it.
            // Wait, reliableCorrelations filters by mag >= 5.0. If backend added an FP entry with no mag, it might be filtered out?
            // Need to check backend change again.
            // Backend sets: earthquake_magnitude: None. parseFloat(None) = NaN. NaN >= 5.0 is false.
            // So reliableCorrelations will be EMPTY for FP/Pending entries.
            // I need to check eqCorrelations for non-EQ entries (status entries).
            const statusEntry = eqCorrelations.find(eq => eq.status);
            if (statusEntry) {
                const status = statusEntry.status;
                const label = status === 'FP' ? 'False Positive' : (status === 'Pending' ? 'Pending' : 'Evaluation unavailable');
                popupContent += `<hr style="margin: 8px 0; border-color: #e74c3c;"><strong style="color: #e74c3c;">${label}</strong><br>`;
                popupContent += status === 'FP' ? `No EQ M≥5.0 within 200km within 14 days` : (status === 'Pending' ? `Monitoring for upcoming EQ...` : `Earthquake evaluation unavailable`);
            } else {
                popupContent += `<hr style="margin: 8px 0; border-color: #e74c3c;"><strong style="color: #e74c3c;">Evaluation unavailable</strong><br>`;
                popupContent += `No completed earthquake evaluation recorded`;
            }
        }
    } else {
        popupContent += `<hr style="margin: 8px 0; border-color: var(--text-secondary);"><span>Status: ${!stationData ? 'Data unavailable or invalid' : `${observationRecordLabel(stationData)} · no anomaly recorded`}</span><br>`;
        if (hasFN) {
            popupContent += `<hr style="margin: 8px 0; border-color: #c0392b;"><strong style="color: #c0392b;">❌ False Negative</strong><br>`;
            popupContent += `${falseNegatives.length} EQ(s) missed:<br>`;
            falseNegatives.forEach(eq => {
                const time = typeof eq.earthquake_time === 'string' ? eq.earthquake_time.split('T')[0] : eq.earthquake_time;
                popupContent += `🔴 M${eq.earthquake_magnitude} on ${time}<br>`;
            });
        } else {
            popupContent += `No anomalies detected`;
        }
    }
    popupContent += `</div>`;

    // Add marker to map
    const marker = L.marker([metadata.latitude, metadata.longitude], { icon })
        .addTo(map)
        .bindPopup(popupContent);

    markers[stationCode] = marker;

    // Add 200km red dashed circle on hover
    let hoverCircle = null;

    marker.on('mouseover', function () {
        if (hoverCircle) {
            map.removeLayer(hoverCircle);
        }
        hoverCircle = L.circle([metadata.latitude, metadata.longitude], {
            color: '#e74c3c',
            weight: 2,
            opacity: 0.8,
            fillColor: '#e74c3c',
            fillOpacity: 0.1,
            radius: 200000,
            dashArray: '10, 10',
            interactive: false // Allow events to pass through
        }).addTo(map);
    });

    marker.on('mouseout', function () {
        if (hoverCircle) {
            map.removeLayer(hoverCircle);
            hoverCircle = null;
        }
    });
}

function getEarthquakeColor(magnitude) {
    // Color gradient based on magnitude
    if (magnitude >= 8.0) return '#c0392b';  // Dark red for M8.0+
    if (magnitude >= 7.0) return '#e74c3c';  // Red for M7.0-7.9
    if (magnitude >= 6.0) return '#e67e22';  // Orange for M6.0-6.9
    return '#f1c40f';  // Yellow for M5.0-5.9
}


// ===== CHART FUNCTIONS =====
let charts = {};

function updateChart(existing, canvas, configuration) {
    if (!existing) return new Chart(canvas, configuration);
    existing.data = configuration.data;
    existing.options = configuration.options;
    existing.update('none');
    return existing;
}

function destroyCharts() {
    Object.values(charts).forEach(chart => {
        if (chart) chart.destroy();
    });
    charts = {};
}

function getChartColors() {
    const isDark = document.body.classList.contains('dark-mode');
    return {
        text: isDark ? '#b3c7d0' : '#657b87',
        grid: isDark ? '#2a3c49' : '#e7edf0',
        unknown: isDark ? '#2f4553' : '#e1e8ec',
        primary: isDark ? '#73ced0' : '#147d83',
        success: isDark ? '#34c38f' : '#1f8a5b',
        warning: isDark ? '#d9b16f' : '#b88943',
        danger: isDark ? '#f87171' : '#dc2626',
        gray: isDark ? '#94a3b8' : '#94a3b8'
    };
}

async function create7DayTrendChart(data, isCurrent = () => true) {
    const ctx = document.getElementById('trend-chart');
    if (!ctx) return;

    const colors = getChartColors();
    const dates = data.available_dates.filter(date => !data.selected_date || date <= data.selected_date).slice(0, 7).sort();
    const anomalyCounts = await parallelMap(dates, async date => {
        try {
            const snapshot = await cachedData(`data/aggregated_${date}.json`);
            return Object.values(snapshot.stations || {}).filter(station =>
                station.date === date && station.is_anomalous).length;
        } catch (error) {
            console.warn(`Trend data unavailable: ${date}`, error);
            return null;
        }
    });

    if (!isCurrent()) return;
    charts.trend = updateChart(charts.trend, ctx, {
        type: 'bar',
        data: {
            labels: dates.map(d => new Date(`${d}T00:00:00Z`).toLocaleDateString('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric' })),
            datasets: [{
                label: 'Anomalies',
                data: anomalyCounts,
                backgroundColor: colors.primary,
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { stepSize: 1, color: colors.text },
                    grid: { color: colors.grid }
                },
                x: {
                    ticks: { color: colors.text },
                    grid: { display: false }
                }
            }
        }
    });
}

function createStationDistributionChart(normalCount, withEqCount, falseAlarmCount, unresolved = 0) {
    const ctx = document.getElementById('distribution-chart');
    if (!ctx) return;

    const colors = getChartColors();

    charts.distribution = updateChart(charts.distribution, ctx, {
        type: 'doughnut',
        data: {
            labels: ['No anomaly', 'Matched', 'False positive', 'Unresolved'],
            datasets: [{
                data: [normalCount, withEqCount, falseAlarmCount, unresolved],
                backgroundColor: [colors.gray, colors.warning, colors.danger, colors.unknown],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: colors.text, padding: 10, font: { size: 11 } }
                }
            }
        }
    });
}

function createDetectionRateChart(successRate) {
    const ctx = document.getElementById('success-rate-chart');
    if (!ctx) return;

    const colors = getChartColors();

    charts.successRate = updateChart(charts.successRate, ctx, {
        type: 'doughnut',
        data: {
            labels: ['Matched anomalies', 'Unmatched anomalies'],
            datasets: [{
                data: successRate === null ? [0, 0] : [successRate, 100 - successRate],
                backgroundColor: [colors.success, colors.grid],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => context.label + ': ' + context.parsed + '%'
                    }
                }
            }
        },
        plugins: [{
            afterDraw: (chart) => {
                const ctx = chart.ctx;
                const centerX = (chart.chartArea.left + chart.chartArea.right) / 2;
                const centerY = (chart.chartArea.top + chart.chartArea.bottom) / 2;
                ctx.save();
                ctx.font = '500 23px \"IBM Plex Mono\", monospace';
                ctx.fillStyle = getChartColors().text;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                const rate = chart.data.datasets[0].data.reduce((a, b) => a + b, 0) === 0 ? null : chart.data.datasets[0].data[0];
                ctx.fillText(rate === null ? 'N/A' : Math.round(rate) + '%', centerX, centerY);
                ctx.restore();
            }
        }]
    });
}

async function createMagnitudeDistributionChart(selectedDate, isCurrent = () => true) {
    const ctx = document.getElementById('magnitude-chart');
    if (!ctx) return;

    const colors = getChartColors();
    const earthquakes = await loadRecentEarthquakes(selectedDate);
    if (!isCurrent()) return;

    const magRanges = { 'M5-5.9': 0, 'M6-6.9': 0, 'M7-7.9': 0, 'M8+': 0 };
    earthquakes.forEach(eq => {
        const mag = parseFloat(eq.magnitude || eq.earthquake_magnitude || 0);
        if (mag >= 8.0) magRanges['M8+']++;
        else if (mag >= 7.0) magRanges['M7-7.9']++;
        else if (mag >= 6.0) magRanges['M6-6.9']++;
        else if (mag >= 5.0) magRanges['M5-5.9']++;
    });

    charts.magnitude = updateChart(charts.magnitude, ctx, {
        type: 'bar',
        data: {
            labels: Object.keys(magRanges),
            datasets: [{
                label: 'Count',
                data: Object.values(magRanges),
                backgroundColor: [colors.primary, colors.success, colors.warning, colors.danger],
                borderRadius: 6
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    ticks: { stepSize: 1, color: colors.text },
                    grid: { color: colors.grid }
                },
                y: {
                    ticks: { color: colors.text },
                    grid: { display: false }
                }
            }
        }
    });
}

async function createAnalyticsCharts(data, normalCount, withEqCount, falseAlarmCount, successRate, unresolved = 0, isCurrent = () => true) {
    await create7DayTrendChart(data, isCurrent);
    if (!isCurrent()) return;
    createStationDistributionChart(normalCount, withEqCount, falseAlarmCount, unresolved);
    createDetectionRateChart(successRate);
    await createMagnitudeDistributionChart(data.selected_date, isCurrent);
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

        // Get color based on magnitude
        const eqColor = getEarthquakeColor(mag);

        // Create earthquake icon with magnitude-based color
        const icon = L.divIcon({
            className: 'earthquake-marker',
            html: `<div class="eq-marker" style="
                width: ${Math.max(20, Math.min(40, mag * 5))}px;
                height: ${Math.max(20, Math.min(40, mag * 5))}px;
                background: ${eqColor};
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

        // Source earthquake timestamps are UTC even when the CSV omits its suffix.
        const times = earthquakeTimes(time, lon);
        const timeStr = times
            ? `${times.utc}<br><small style="color: #666;">Local (approx): ${times.local}</small>`
            : 'Unknown';

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
        marker.on('click', function () {
            if (!map.hasLayer(circle)) {
                circle.addTo(map);
            }
        });

        marker.on('mouseover', function () {
            if (!map.hasLayer(circle)) {
                circle.addTo(map);
            }
        });

        marker.on('mouseout', function () {
            // Keep circle visible on click, only hide on mouseout if not clicked
            // We'll track if it was clicked
            if (!marker._clicked) {
                if (map.hasLayer(circle)) {
                    map.removeLayer(circle);
                }
            }
        });

        // Track click state
        marker.on('click', function () {
            marker._clicked = true;
        });

        // Hide circle when popup closes
        marker.on('popupclose', function () {
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

function createStandaloneLegend() {
    const legend = document.getElementById('map-legend');
    if (!legend) return;
    legend.innerHTML = `<div class="legend-row"><span><i class="legend-dot"></i>No anomaly / unavailable</span><span><i class="legend-dot matched"></i>Matched anomaly</span><span><i class="legend-dot false"></i>False positive</span><span class="legend-scale">EVENTS M ≥ 5.0</span></div>`;
}

function refreshChartTheme() {
    const colors = getChartColors();
    [...Object.values(charts), ...stationCharts].forEach(chart => {
        if (chart.options.scales) Object.values(chart.options.scales).forEach(scale => {
            if (scale.ticks) scale.ticks.color = colors.text;
            if (scale.grid) scale.grid.color = colors.grid;
        });
        if (chart.options.plugins?.legend?.labels) chart.options.plugins.legend.labels.color = colors.text;
        chart.update('none');
    });
}

function resetObservationDisplay(message = 'Loading observations…') {
    // Invalidate pending station selections as well as the old visible snapshot.
    stationPlotGeneration++;
    stationCharts.forEach(chart => chart.destroy());
    stationCharts = [];
    destroyCharts();
    if (map) { map.remove(); map = null; }
    markers = {};
    allStationsData = {};
    document.querySelectorAll('.fallback-notice').forEach(notice => notice.remove());
    const summary = document.getElementById('summary-stats');
    if (summary) { summary.innerHTML = ''; summary.setAttribute('aria-busy', 'false'); }
    const health = document.getElementById('run-health');
    if (health) { health.innerHTML = ''; health.style.display = 'none'; }
    const panel = document.getElementById('selected-station-plot');
    if (panel) panel.innerHTML = `<div class="empty-state">${escapeText(message)}</div>`;
    const legend = document.getElementById('map-legend');
    if (legend) legend.innerHTML = '';
    const timestamp = document.getElementById('timestamp');
    if (timestamp) timestamp.textContent = message;
    const stationSelector = document.getElementById('station-selector');
    if (stationSelector) stationSelector.disabled = true;
    const download = document.getElementById('download-anomalies-btn');
    if (download) download.disabled = true;
}

async function renderDashboard(date = null, {refresh = false} = {}) {
    const generation = ++dashboardGeneration;
    const isCurrent = () => generation === dashboardGeneration;
    if (refresh) invalidateDataRequests();
    else if (displayedDate) {
        // Revalidate current observations; historical trend snapshots remain bounded.
        dataRequests.delete(DATA_URL);
        if (date) dataRequests.delete(`data/aggregated_${date}.json`);
    }
    const preserveView = Boolean(map && displayedDate);
    stationPlotGeneration++;
    if (!preserveView) resetObservationDisplay();
    const summarySection = document.getElementById('summary-stats');
    if (summarySection) summarySection.setAttribute('aria-busy', 'true');
    const healthSection = document.getElementById('run-health');
    if (preserveView && healthSection) healthSection.setAttribute('aria-label', 'Previous observations; loading selected date');
    if (preserveView) {
        const timestamp = document.getElementById('timestamp');
        if (timestamp) timestamp.textContent = 'Loading selected observations… previous values remain visible';
    }
    const exportControl = document.getElementById('download-anomalies-btn');
    if (exportControl) exportControl.disabled = true;
    const stationControl = document.getElementById('station-selector');
    if (stationControl) stationControl.disabled = true;
    console.log('renderDashboard called with date:', date);
    // The template already has the structure, we just need to update it
    // Show loading state
    const mapContainer = document.getElementById('map-container');
    if (mapContainer && !preserveView) {
        mapContainer.innerHTML = '<div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-primary);"><p>Loading map data...</p></div>';
    }

    let data;
    try {
        console.log('Loading data...');
        data = await loadData(date, isCurrent);
        if (!isCurrent()) return;
        console.log('Data loaded:', data ? 'Success' : 'Failed', data);

        if (!data) {
            displayedSnapshotSignature = null;
            displayedDate = null;
            resetObservationDisplay('Observations unavailable. Select another date or retry.');
            const dateStr = date || selectedDate || 'selected date';
            console.warn('No data available for date:', dateStr);
            if (mapContainer) {
                mapContainer.innerHTML = `
                    <div class="no-data" style="text-align: center; padding: 40px; color: var(--text-primary);">
                        <h2 style="color: #e74c3c; margin-bottom: 20px;">⚠️ No Data Available</h2>
                        <p style="font-size: 1.1em; margin-bottom: 10px;">
                            Observations could not be loaded for <strong>${escapeText(dateStr)}</strong>.
                        </p>
                        <p style="color: var(--text-secondary); font-size: 0.9em;">
                            Please select a different date from the dropdown above.
                        </p>
                    </div>
                `;
            }
            return;
        }
    } catch (error) {
        if (!isCurrent()) return;
        resetObservationDisplay('Observations unavailable. Select another date or retry.');
        console.error('Error in renderDashboard:', error);
        if (mapContainer) {
            mapContainer.innerHTML = `
                <div class="error" style="text-align: center; padding: 40px; color: #e74c3c;">
                    <h2 style="margin-bottom: 20px;">❌ Error Loading Data</h2>
                    <p style="font-size: 1.1em; margin-bottom: 10px;">
                        ${escapeText(error.message || 'Unknown error occurred')}
                    </p>
                    <p style="color: var(--text-secondary); font-size: 0.9em;">
                        Please check the browser console for details.
                    </p>
                </div>
            `;
        }
        return;
    }

    // Revalidate every dependency on a scheduled refresh, then avoid allocating
    // new UI objects when the values and classifications are unchanged.
    const trendDates = data.available_dates.filter(day => day <= data.selected_date).slice(0, 7);
    const contextValues = await Promise.all([
        getAnomalyHistory(), getFalseNegativeHistory(),
        cachedData(`data/earthquake_stats_${data.selected_date}.json`).catch(() => null),
        loadRecentEarthquakes(data.selected_date),
        parallelMap(trendDates, day => cachedData(`data/aggregated_${day}.json`).catch(() => null))
    ]);
    if (!isCurrent()) return;
    const comparableContext = [...contextValues.slice(0, 4), contextValues[4].map(snapshot =>
        snapshot ? {date: snapshot.date, stations: snapshot.stations} : null)];
    const snapshotSignature = JSON.stringify([data.data, data.station_quality, data.metadata,
        window.earthquakeCorrelations, window.falseNegatives, data.selected_date,
        data.available_dates, data.most_recent_date, data.station_dates, data.is_hybrid_aggregation, comparableContext]);
    if (preserveView && snapshotSignature === displayedSnapshotSignature) {
        if (summarySection) summarySection.setAttribute('aria-busy', 'false');
        if (healthSection) healthSection.setAttribute('aria-label', 'Data quality and availability');
        if (exportControl) exportControl.disabled = false;
        if (stationControl) stationControl.disabled = false;
        updateSnapshotTimestamp(data);
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
            notice.style.cssText = 'background: rgba(243, 156, 18, 0.15); border-left: 4px solid #f39c12; padding: 16px 20px; margin: 15px 0; border-radius: 8px; color: var(--text-primary); font-size: 0.95rem;';

            let noticeHTML = `<div style="display: flex; align-items: flex-start; gap: 12px;">`;
            noticeHTML += `<div style="font-size: 1.5em;">ℹ️</div>`;
            noticeHTML += `<div style="flex: 1;">`;
            noticeHTML += `<strong style="color: var(--accent-warning); display: block; margin-bottom: 8px;">Data Availability Notice</strong>`;
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
                noticeHTML += `Some stations are showing previous-night observations. Their actual dates are listed above; this is separate from threshold calibration.`;
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
            if (date === data.selected_date) {
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
            if (!isCurrent()) return;
            // Filter by magnitude >= 5.0 for reliability
            const reliableCorrelations = eqCorrelations.filter(isConfirmedCorrelation);
            if (reliableCorrelations.length > 0) {
                withEQ++;
            }

            // Allow FP/Pending status entries to pass through to map
            let mapCorrelations = reliableCorrelations;
            const statusEntries = eqCorrelations.filter(eq => ['FP', 'Pending', 'Unknown'].includes(eq.status));
            if (statusEntries.length > 0) {
                mapCorrelations = [...reliableCorrelations, ...statusEntries];
            }

            // Note: False positives are collected in the cumulative loop below (lines 983-1037)
            // to avoid double-counting when the same date is processed multiple times
            stationDataMap[station] = { stationData, eqCorrelations: mapCorrelations };
        } else {
            // Note: False negatives are collected in the cumulative loop below (lines 978-1032)
            // to avoid double-counting when the same date is processed multiple times
            const fn = await loadFalseNegatives(station, data.selected_date);
            if (!isCurrent()) return;
            stationDataMap[station] = { stationData, eqCorrelations: [], falseNegatives: fn };
        }
    }

    // For cumulative false positives/negatives since Nov 18, 2025
    const ANALYSIS_START_DATE = '2025-11-18';
    let falseAlarms = 0;
    let falseNegatives = 0;
    let unverifiedFalseNegatives = 0;
    let latestFalsePositiveDate = null;
    let latestFalseNegativeDate = null;
    try {
        const [anomalyHistory, falseNegativeHistory] = await Promise.all([
            getAnomalyHistory(),
            getFalseNegativeHistory()
        ]);
        if (!isCurrent()) return;

        const anomalyEntries = Array.isArray(anomalyHistory?.entries) ? anomalyHistory.entries : [];
        const falseNegativeEntries = Array.isArray(falseNegativeHistory?.entries) ? falseNegativeHistory.entries : [];

        // Deduplicate false positives by station+date to fix inflated count
        const falsePositiveEntries = anomalyEntries.filter(isConfirmedFalsePositive);
        const uniqueFalsePositives = new Map();
        falsePositiveEntries.forEach(entry => {
            const key = `${entry.station}_${entry.date}`;
            if (!uniqueFalsePositives.has(key)) {
                uniqueFalsePositives.set(key, entry);
            }
        });
        falseAlarms = uniqueFalsePositives.size;  // Only count unique station+date combos

        if (uniqueFalsePositives.size > 0) {
            const sortedFP = Array.from(uniqueFalsePositives.values())
                .sort((a, b) => (b.date || '').localeCompare(a.date || ''));
            latestFalsePositiveDate = sortedFP[0]?.date || null;
        }

        falseNegatives = falseNegativeEntries.length;
        unverifiedFalseNegatives = falseNegativeEntries.filter(entry => entry.coverage_verified !== true).length;
        if (falseNegativeEntries.length > 0) {
            const sortedFN = [...falseNegativeEntries].sort((a, b) => {
                const aTime = (a.earthquake_time || a.date || '').toString();
                const bTime = (b.earthquake_time || b.date || '').toString();
                return bTime.localeCompare(aTime);
            });
            const latestFN = sortedFN[0];
            if (latestFN) {
                const fnTime = latestFN.earthquake_time || latestFN.date;
                latestFalseNegativeDate = typeof fnTime === 'string' ? fnTime.split('T')[0] : fnTime;
            }
        }
    } catch (historyError) {
        console.debug('Unable to load history files for cumulative metrics:', historyError);
    }

    // Load earthquake statistics for selected date only (no fallback)
    let eqStats = { global: null, within200km: null };

    // Only try the selected date
    try {
        const statsData = contextValues[2];
        if (statsData) {
            eqStats = {
                global: validEventCount(statsData.global_count ?? statsData.global),
                within200km: validEventCount(statsData.within_200km_count ?? statsData.within200km)
            };
        }
    } catch (error) {
        console.debug('Could not load earthquake statistics for selected date:', error);
    }
    if (!isCurrent()) return;
    displayedDate = data.selected_date;

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
                <div class="value">${eqStats.global ?? 'N/A'}</div>
                <div class="label">Global · M ≥ 5.0</div>
                <div class="sub-label" style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
                    ${eqStats.within200km === null ? 'Event statistics unavailable' : `${eqStats.within200km} within 200km of stations`}
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
                    Since: ${formatDateForSelector(ANALYSIS_START_DATE)}${latestFalseNegativeDate ? `<br>Latest: ${formatDateForSelector(latestFalseNegativeDate)}` : ''}${unverifiedFalseNegatives ? `<br>${unverifiedFalseNegatives} historical records · coverage not established` : ''}
                </div>
            </div>
        `;
    }

    // Update timestamp will be handled in renderDashboard

    // Update station selector dropdown
    const stationSelector = document.getElementById('station-selector');
    if (stationSelector) {
        const previousStation = stationSelector.value;
        stationSelector.innerHTML = '<option value="">Select a station...</option>';

        // Add anomalous stations first
        anomalousStations.forEach(station => {
            const metadata = stationMetadata[station] || {};
            const stationData = allStationsData[station];
            const eqCorrelations = stationDataMap[station]?.eqCorrelations || [];
            const hasEQ = eqCorrelations.some(isConfirmedCorrelation);
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
            option.textContent = `${station} - ${metadata.name || station} (${observationRecordLabel(allStationsData[station])})`;
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
        const defaultStation = previousStation && allStations.includes(previousStation) ? previousStation : (anomalousStations[0] || (allStationsData.KAK ? 'KAK' : Object.keys(allStationsData)[0]));
        if (defaultStation) {
            stationSelector.value = defaultStation;
            await renderStationPlot(defaultStation);
            if (!isCurrent()) return;
        }

        // Create analytics charts
        const loaded = Object.keys(allStationsData).length;
        const normalStations = loaded - anomalousCount;
        const currentFalseAlarms = Object.values(stationDataMap).filter(item => item.eqCorrelations.some(eq => eq.status === 'FP')).length;
        const unresolved = totalStations - loaded + anomalousCount - withEQ - currentFalseAlarms;
        const detectionRate = anomalousCount > 0 ? Math.round((withEQ / anomalousCount) * 100) : null;
        await createAnalyticsCharts(data, normalStations, withEQ, currentFalseAlarms, detectionRate, unresolved, isCurrent);
        if (!isCurrent()) return;
        stationSelector.disabled = false;
    }
    const download = document.getElementById('download-anomalies-btn');
    if (download) download.disabled = false;

    // Initialize map - wait a bit for DOM to be ready
    await (async () => {
        if (!isCurrent()) return;
        const mapEl = document.getElementById('map-container');
        if (!mapEl) {
            console.error('Map container not found');
            return;
        }

        // Clear any loading message
        if (!map) mapEl.innerHTML = '';

        // Ensure container has dimensions
        if (mapEl.offsetHeight === 0) {
            console.warn('Map container has no height, setting minimum height');
            mapEl.style.minHeight = '600px';
        }

        try {
            console.log('Initializing map...');
            if (!map) initMap();
            else clearMapObservations();

            if (!map) {
                console.error('Map initialization failed');
                mapEl.innerHTML = '<div style="padding: 20px; color: #e74c3c;">Failed to initialize map</div>';
                return;
            }

            // Wait for map to be ready
            await new Promise(resolve => map.whenReady(resolve));
            if (!isCurrent()) return;

            console.log('Adding station markers...', allStations.length);
            // Add all station markers
            for (const station of allStations) {
                const mapData = stationDataMap[station] || { stationData: allStationsData[station], eqCorrelations: [], falseNegatives: [] };
                addStationToMap(station, mapData.stationData, mapData.eqCorrelations, data, mapData.falseNegatives);
            }

            console.log('Loading earthquakes...');
            // Add earthquake markers
            const recentEarthquakes = contextValues[3];
            if (!isCurrent()) return;
            console.log('Loaded earthquakes for map:', recentEarthquakes.length, recentEarthquakes);
            addEarthquakeMarkers(recentEarthquakes);

            // Create standalone legend outside the map
            createStandaloneLegend();

            // Invalidate map size to ensure it renders correctly
            if (isCurrent() && map) map.invalidateSize();
        } catch (error) {
            if (!isCurrent()) return;
            console.error('Error initializing map:', error);
            mapEl.innerHTML = `<div style="padding: 20px; color: #e74c3c;">Error loading map: ${error.message}<br><small>${error.stack}</small></div>`;
        }
    })();
    if (!isCurrent()) return;
    displayedSnapshotSignature = snapshotSignature;
    if (summarySection) summarySection.setAttribute('aria-busy', 'false');
    if (healthSection) healthSection.setAttribute('aria-label', 'Data quality and availability');

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

    // Update Run Health / Data Availability
    const availableStationsCount = allStations.filter(s => allStationsData[s]).length;
    updateRunHealth(data, allStations.length, availableStationsCount);

    // Update timestamp (UTC-based)
    updateSnapshotTimestamp(data);
}

function updateSnapshotTimestamp(data) {
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
            // Do not label an old snapshot with the current clock time.
            timestampEl.textContent = new Date(data.generated_at || 0).toLocaleString('en-US', {
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

function escapeText(value) {
    return String(value ?? '').replace(/[&<>"']/g, character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
}

function stationHour(stamp, timezone = 'UTC') {
    const utc = /(?:Z|[+-]\d{2}:\d{2})$/.test(stamp) ? stamp : `${stamp}Z`;
    const date = new Date(utc);
    if (!Number.isFinite(date.getTime())) return '';
    // Hourly windows are saved one second before their midpoint.
    date.setSeconds(date.getSeconds() + 1);
    return new Intl.DateTimeFormat('en-GB', {hour: '2-digit', minute: '2-digit', timeZone: timezone}).format(date);
}

function recordedValues(values = []) {
    return values.map(value => value === null || value === undefined || !Number.isFinite(Number(value)) ? null : Number(value));
}

function drawStationCharts(station, data) {
    if (typeof Chart === 'undefined') return;
    const colors = getChartColors();
    const labels = (data.timestamps || []).map(stamp => stationHour(stamp, stationMetadata[station]?.timezone || 'UTC'));
    const axes = {
        x: { grid: {display: false}, border: {display: false}, ticks: {maxTicksLimit: 5, color: colors.text, font: {family: 'IBM Plex Mono', size: 8}, maxRotation: 0} },
        y: { grid: {color: colors.grid, drawTicks: false}, border: {display: false}, ticks: {maxTicksLimit: 4, color: colors.text, font: {family: 'IBM Plex Mono', size: 8}} }
    };
    const options = {responsive: true, maintainAspectRatio: false, animation: false,
        interaction: {mode: 'index', intersect: false},
        plugins: {legend: {display: false}, tooltip: {backgroundColor: '#183542', titleFont: {family: 'DM Sans'}, bodyFont: {family: 'IBM Plex Mono', size: 10}}},
        scales: axes};
    const threshold = Number.isFinite(Number(data.threshold)) ? Number(data.threshold) : null;
    stationCharts[0] = updateChart(stationCharts[0], document.getElementById('station-ratio-chart'), {
        type: 'line', data: {labels, datasets: [
            {label: 'Polarization ratio P', data: recordedValues(data.P), borderColor: colors.primary, backgroundColor: 'rgba(20,125,131,.045)', fill: true, borderWidth: 1.6, pointRadius: 2.2, pointHoverRadius: 4, tension: 0},
            {label: 'Threshold', data: labels.map(() => threshold), borderColor: colors.warning, borderDash: [4, 4], borderWidth: 1, pointRadius: 0}
        ]}, options: structuredClone(options)
    });
    const powerOptions = structuredClone(options);
    powerOptions.scales.y.ticks.callback = value => Math.abs(value) > 0 && (Math.abs(value) < .01 || Math.abs(value) >= 10000) ? Number(value).toExponential(0) : value;
    stationCharts[1] = updateChart(stationCharts[1], document.getElementById('station-power-chart'), {
        type: 'line', data: {labels, datasets: [
            {label: 'Vertical S_Z', data: recordedValues(data.nZ), borderColor: colors.primary, borderWidth: 1.3, pointRadius: 0, tension: 0},
            {label: 'Horizontal S_G', data: recordedValues(data.nG), borderColor: '#8b9eab', borderWidth: 1.3, pointRadius: 0, borderDash: [3, 3], tension: 0}
        ]}, options: powerOptions
    });
}

function observationRecordLabel(data) {
    if (!data) return 'Unavailable';
    const quality = data.data_quality?.status;
    if (quality === 'complete') return 'Complete observation';
    if (quality === 'partial') return 'Partial observation';
    return 'Historical observation';
}

function observationStatusText(data) {
    const record = observationRecordLabel(data);
    return record === 'Historical observation'
        ? `${record} · no anomaly recorded; coverage not recorded`
        : `${record} · no anomaly recorded`;
}

function thresholdBaselineLabel(data) {
    if (data.baseline_window_days !== 14) return 'Recorded threshold · historical settings';
    const nights = Number(data.baseline_historical_nights || 0) + (data.baseline_includes_observation ? 1 : 0);
    return `14-night threshold · ${nights}/14 nights used · ${data.baseline_samples || 0} quiet hours`;
}

async function renderStationPlot(stationCode) {
    const generation = ++stationPlotGeneration;
    const dashboard = dashboardGeneration;
    const panel = document.getElementById('selected-station-plot');
    if (!panel) return;
    const data = allStationsData[stationCode];
    const metadata = stationMetadata[stationCode] || {};
    if (!data) {
        stationCharts.forEach(chart => chart.destroy());
        stationCharts = [];
        panel.innerHTML = `<div class="empty-state"><strong>${escapeText(stationCode)} · Observation unavailable</strong><br>No usable measurements for this observation date. Select another station.</div>`;
        return;
    }
    const correlations = await loadEarthquakeCorrelations(stationCode, data.date);
    if (generation !== stationPlotGeneration || dashboard !== dashboardGeneration) return;
    const matched = correlations.some(isConfirmedCorrelation);
    const hasAnomaly = data.is_anomalous;
    const complete = data.data_quality?.status === 'complete';
    const status = hasAnomaly ? (matched ? 'Matched anomaly' : (correlations.some(row => row.status === 'FP') ? 'False positive · 14-day window complete' : 'Anomaly · evaluation pending or unavailable')) : observationStatusText(data);
    const coordinates = Number.isFinite(metadata.latitude) && Number.isFinite(metadata.longitude) ? `${metadata.latitude.toFixed(2)}°, ${metadata.longitude.toFixed(2)}°` : '';
    const threshold = Number.isFinite(Number(data.threshold)) ? Number(data.threshold).toPrecision(4) : 'N/A';
    const figure = `figures/${encodeURIComponent(stationCode)}/PRA_${encodeURIComponent(stationCode)}_${data.date.replace(/-/g, '')}.png`;
    const method = data.threshold_method === 'evt' ? 'EVT GPD' : (data.threshold_method === 'k_sigma' ? 'k-sigma fallback' : 'Threshold method not recorded');
    const replacement = document.createElement('div');
    replacement.innerHTML = `
        <div class="station-identity"><h3><b>${escapeText(stationCode)}</b> ${escapeText(metadata.name || stationCode)}</h3><span class="coordinates">${escapeText(coordinates)}</span></div>
        <div class="observation-tag ${complete ? 'verified' : ''}">${escapeText(status)}</div>
        <div class="plot-label"><b>Polarization ratio</b><span class="series-key"><span><i></i>P</span><span><i class="threshold"></i>Threshold ${escapeText(threshold)}</span></span></div>
        <div class="station-chart"><canvas id="station-ratio-chart" role="img" aria-label="Hourly polarization ratio and threshold at ${escapeText(stationCode)}"></canvas></div>
        <hr class="station-separator">
        <div class="plot-label"><b>Spectral band powers</b><span class="series-key"><span><i></i>S<sub>Z</sub></span><span><i class="horizontal"></i>S<sub>G</sub></span></span></div>
        <div class="station-chart power"><canvas id="station-power-chart" role="img" aria-label="Recorded vertical and horizontal band powers"></canvas></div>
        <div class="station-footnote"><span>${escapeText(data.date)} · ${escapeText(metadata.timezone || 'UTC')}<br>${escapeText(method)}${data.baseline_source === 'warmup' ? ' · warmup' : ''}<br>${escapeText(thresholdBaselineLabel(data))}</span><a href="${figure}" target="_blank" rel="noopener noreferrer">Original figure ↗</a></div>`;
    if (data.date !== selectedDate) replacement.insertAdjacentHTML('afterbegin', `<div class="observation-tag">Showing ${escapeText(data.date)}; selected ${escapeText(selectedDate)}</div>`);
    for (const canvas of replacement.querySelectorAll('canvas')) {
        const existing = panel.querySelector(`#${canvas.id}`);
        if (existing) canvas.replaceWith(existing);
    }
    panel.replaceChildren(...replacement.childNodes);
    drawStationCharts(stationCode, data);
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
        const hasEQ = eqCorrelations.some(isConfirmedCorrelation);

        html += '<tr>';
        html += `<td><strong>${station}</strong></td>`;
        html += `<td>${metadata.name || station}</td>`;
        html += `<td>${metadata.country || '-'}</td>`;

        if (hasAnomaly) {
            html += `<td><span class="badge badge-danger">⚠️ Anomaly</span></td>`;
            html += `<td>${hasEQ ? '<span class="badge badge-eq">🌋 Yes (' + eqCorrelations.length + ')</span>' : '<span class="badge badge-warning">' + (eqCorrelations.some(eq => eq.status === 'FP') ? 'False Positive' : 'Evaluation pending / unavailable') + '</span>'}</td>`;
        } else {
            html += `<td><span class="badge badge-secondary">${observationRecordLabel(data)}</span></td>`;
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
                                Threshold: stationData.threshold ?? ''
                            };
                            allAnomalies.push(anomaly);
                        }
                    }
                } else if (!isAggregatedDataLoaded) {
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
                    const value = row[header] ?? '';
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
        URL.revokeObjectURL(url);

        console.log(`Downloaded ${allAnomalies.length} anomalies`);
    } catch (error) {
        console.error('Error downloading anomalies CSV:', error);
        alert('Error downloading anomalies CSV. Please try again.');
    }
}

function updateRunHealth(data, totalStationsCount, loadedStationsCount) {
    const healthEl = document.getElementById('run-health');
    if (!healthEl) return;

    if (!data) {
        healthEl.style.display = 'none';
        return;
    }

    healthEl.style.display = 'flex';

    // Calculate availability percentage
    const availabilityPct = totalStationsCount > 0 ? Math.round((loadedStationsCount / totalStationsCount) * 100) : 0;
    const isHybrid = data.is_hybrid_aggregation || false;
    const qualities = Object.values(data.station_quality || {});
    const completeCount = qualities.filter(value => value === 'complete').length;
    const historicalCount = qualities.filter(value => ['unverified', 'historical'].includes(value)).length;
    const partialCount = qualities.filter(value => value === 'partial').length;

    healthEl.innerHTML = `
        <div class="health-heading"><h3><i class="status-dot ${availabilityPct < 90 ? 'partial' : ''}"></i>Data availability</h3><p>Observation quality &amp; provenance</p></div>
        <div class="health-grid">
            <div class="health-item"><div class="health-label">Usable observations</div><div class="health-value"><b>${loadedStationsCount} / ${totalStationsCount}</b> stations <span class="health-meta">· ${availabilityPct}%</span></div><div class="coverage-meter"><span style="width:${availabilityPct}%"></span></div></div>
            <div class="health-item"><div class="health-label">Observation records</div><div class="health-value">${completeCount} complete <span class="health-meta">/ ${partialCount} partial / ${historicalCount} historical</span></div><div class="health-meta">Historical completeness not recorded · invalid records excluded</div></div>
            <div class="health-item"><div class="health-label">Observation window</div><div class="health-value">${formatDate(data.selected_date)}</div><div class="health-meta">${isHybrid ? 'Includes clearly dated previous-night data' : 'Canonical station-night snapshots'}</div></div>
        </div>`;
}
