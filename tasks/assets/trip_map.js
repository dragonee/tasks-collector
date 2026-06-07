// Trip detail map: plot every POI (note or photo) from the trip's journal on
// an OpenStreetMap (Leaflet) map in the left column, cross-linked with the
// history list on the right.
//
//   - photos render as a small circular miniature, notes as a pin dot;
//   - dense areas collapse into clusters (leaflet.markercluster);
//   - clicking a marker selects + scrolls its entry in the history;
//   - clicking a cluster filters the history down to that cluster's entries.
//
// Coordinates are parsed server-side (see _map_points in views_trip.py) and
// handed to us as JSON, so we never depend on the comment DOM that app.js
// rewrites.

import L from 'leaflet';
import 'leaflet.markercluster';

import 'leaflet/dist/leaflet.css';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import 'leaflet.markercluster/dist/MarkerCluster.Default.css';

const mapEl = document.getElementById('trip-map');
const dataEl = document.getElementById('trip-map-data');

// The template only renders the map (and loads this bundle) when the trip has
// located entries, but guard anyway so a stray empty payload is a no-op.
if (mapEl && dataEl) {
    let points = [];
    try {
        points = JSON.parse(dataEl.textContent) || [];
    } catch (e) {
        points = [];
    }

    if (points.length > 0) {
        initMap(points);
    }
}

function initMap(points) {
    const map = L.map(mapEl, { scrollWheelZoom: true });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    // Indexes for cross-linking markers <-> history entries.
    const markersById = new Map();
    const entriesById = new Map();
    document.querySelectorAll('.trip-entry[data-event-id]').forEach((li) => {
        entriesById.set(String(li.dataset.eventId), li);
    });

    const cluster = L.markerClusterGroup({
        // We handle cluster clicks ourselves (filter the history) instead of
        // the default zoom-to-bounds.
        zoomToBoundsOnClick: false,
        maxClusterRadius: 45,
    });

    points.forEach((point) => {
        const marker = L.marker([point.lat, point.lng], { icon: iconFor(point) });
        marker.eventId = String(point.id);
        marker.bindPopup(popupFor(point), { minWidth: 160, maxWidth: 240 });
        marker.on('click', () => selectEntry(marker.eventId));
        markersById.set(marker.eventId, marker);
        cluster.addLayer(marker);
    });

    map.addLayer(cluster);
    fitToAll();

    cluster.on('clusterclick', (event) => {
        const ids = event.layer.getAllChildMarkers().map((m) => m.eventId);
        filterHistory(ids);
        map.fitBounds(event.layer.getBounds(), { padding: [40, 40] });
    });

    // History -> map: tapping a POI pin (the 📍 added by app.js) navigates the
    // embedded map to that coordinate instead of opening an external map site;
    // tapping an entry's body does the same. The photo link/image and buttons
    // keep their own behaviour.
    document.querySelector('.trip-entries main').addEventListener('click', (e) => {
        const li = e.target.closest('.trip-entry[data-event-id]');
        if (!li) {
            return;
        }
        if (e.target.closest('.trip-pin')) {
            e.preventDefault(); // don't follow the external map link
            locateOnMap(li);
            return;
        }
        if (e.target.closest('a, img, button')) {
            return;
        }
        locateOnMap(li);
    });

    function locateOnMap(li) {
        const marker = markersById.get(String(li.dataset.eventId));
        if (!marker) {
            return;
        }
        cluster.zoomToShowLayer(marker, () => marker.openPopup());
        highlightEntry(li);
    }

    const filterBanner = document.getElementById('trip-history-filter');
    if (filterBanner) {
        filterBanner
            .querySelector('.trip-history-filter-reset')
            .addEventListener('click', clearFilter);
    }

    // Leaflet needs a re-measure if the column was still settling at init.
    setTimeout(() => map.invalidateSize(), 0);
    window.addEventListener('resize', () => map.invalidateSize());

    function fitToAll() {
        const bounds = L.latLngBounds(points.map((p) => [p.lat, p.lng]));
        map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
    }

    // Select a single entry from a marker click: clear any filter, scroll the
    // entry into view, highlight it, and open the marker's popup.
    function selectEntry(id) {
        clearFilter();
        const li = entriesById.get(String(id));
        if (!li) {
            return;
        }
        li.scrollIntoView({ block: 'center', behavior: 'smooth' });
        highlightEntry(li);
    }

    function highlightEntry(li) {
        entriesById.forEach((entry) => entry.classList.remove('is-located'));
        li.classList.add('is-located');
    }

    // Cluster click: show only the entries whose ids are in `ids`, collapse
    // day groups that end up empty, and surface a reset banner.
    function filterHistory(ids) {
        const keep = new Set(ids.map(String));
        entriesById.forEach((li, id) => {
            li.classList.toggle('is-filtered-out', !keep.has(id));
        });
        document.querySelectorAll('.trip-day').forEach((day) => {
            const anyVisible = day.querySelector('.trip-entry:not(.is-filtered-out)');
            day.classList.toggle('is-filtered-out', !anyVisible);
        });
        if (filterBanner) {
            filterBanner.querySelector('.trip-history-filter-text').textContent =
                `Showing ${keep.size} of ${points.length} places`;
            filterBanner.classList.remove('hidden');
        }
    }

    function clearFilter() {
        document
            .querySelectorAll('.is-filtered-out')
            .forEach((el) => el.classList.remove('is-filtered-out'));
        if (filterBanner) {
            filterBanner.classList.add('hidden');
        }
    }
}

// A circular photo miniature for photo entries; a small pin dot for notes.
function iconFor(point) {
    if (point.is_photo && point.thumbnail_url) {
        // Render the miniature as a background image on the <span> rather than
        // an <img>: Leaflet's `.leaflet-marker-pane img` rule forces width:auto
        // on marker images, so an <img> won't fill the circle. Setting the
        // presigned S3 URL inline and verbatim (no encodeURI) keeps the SigV4
        // signature intact — encodeURI double-encoded %2F -> %252F (S3 -> 400).
        const span = document.createElement('span');
        span.className = 'trip-map-pin trip-map-pin--photo';
        span.style.backgroundImage = `url("${point.thumbnail_url}")`;
        return L.divIcon({
            className: 'trip-map-marker',
            html: span,
            iconSize: [46, 46],
            iconAnchor: [23, 23],
            popupAnchor: [0, -24],
        });
    }
    return L.divIcon({
        className: 'trip-map-marker',
        html: '<span class="trip-map-pin trip-map-pin--note"></span>',
        iconSize: [22, 22],
        iconAnchor: [11, 11],
        popupAnchor: [0, -10],
    });
}

// Build popup content as DOM nodes so user note text can't inject markup.
function popupFor(point) {
    const root = document.createElement('div');
    root.className = 'trip-popup';

    if (point.is_photo && point.thumbnail_url) {
        const img = document.createElement('img');
        img.className = 'trip-popup-photo';
        img.src = point.thumbnail_url;
        img.alt = '';
        root.appendChild(img);
    }

    const meta = document.createElement('div');
    meta.className = 'trip-popup-meta';
    meta.textContent = [point.date, point.time].filter(Boolean).join(' · ');
    root.appendChild(meta);

    if (point.note) {
        const note = document.createElement('div');
        note.className = 'trip-popup-note';
        note.textContent = point.note;
        root.appendChild(note);
    }

    return root;
}
