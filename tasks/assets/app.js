// App code-base initialistaion goes here.

// Load app-wide styles. Those will affect
// every component. For Vue-component-specific styles
// see scoped CSS.
import "./scripts/shared.js";
import "./app.scss";
import "./observation_search.js";
import "./observation_master_detail.js";
import "./observation_menu.js";
import "./observation_edit.js";
import { autosizeAll, resizeTextarea } from "./autosize.js";

// Grow/shrink every server-rendered textarea to fit its content.
autosizeAll();

const nodeList = document.querySelectorAll(
    'article.observation'
);

[...nodeList].forEach((observation) => {
    const link = document.createElement('span');
    link.classList.add("observation-hide");

    link.addEventListener('click', () => {
        observation.classList.toggle('open');
    })

    observation.appendChild(link);
});

const journalAddedEvents = document.querySelectorAll('.event-content.journal-added');

// An entry's +Breakthrough and +Tag buttons each open a small form under it,
// with its text field prefilled. The buttons step aside while a form is open,
// since they sit over its Save button. The form is looked up on every click:
// htmx swaps it for a fresh one after each save.
const INLINE_FORMS = {
    breakthrough: { button: '.add-breakthrough-button', form: '.habit-form', field: 'text', prefill: '#breakthrough ' },
    tag: { button: '.add-tag-button', form: '.tag-form', field: 'name', prefill: '' },
};

const addInlineFormListener = (event, { button: buttonSelector, form: formSelector, field, prefill }) => {
    const button = event.querySelector(buttonSelector);
    const form = event.querySelector(formSelector);

    // Read-only views (e.g. the trip page) omit these controls.
    if (!button || !form) {
        return;
    }

    button.addEventListener('click', () => {
        form.classList.remove('hidden');
        form.querySelector('form').classList.remove('hidden');

        const textField = form.querySelector(`[name=${field}]`);
        textField.value = prefill;
        textField.focus();
        button.closest('.add-breakthrough').classList.add('hidden');
    })
};

[...journalAddedEvents].forEach((event) => {
    Object.values(INLINE_FORMS).forEach((inlineForm) => addInlineFormListener(event, inlineForm));
});

// Trip notes/photos prepend a machine line like "#poi lat=.. lng=..". Hide
// that line from the rendered comment and surface the coordinates as a small
// map pin instead. The leading token may be #poi/#coords/#coordinates/#latlng.
const POI_LINE_RE = /^#(?:poi|coords|coordinates|latlng)\b[^\n<]*?\blat\s*=\s*(-?\d+(?:\.\d+)?)[^\n<]*?\blng\s*=\s*(-?\d+(?:\.\d+)?)/i;

// Map link for a coordinate, per the user's profile preference (data-map-provider
// on <body>). Defaults to OpenStreetMap.
const mapUrlFor = (lat, lng) => {
    const provider = document.body.dataset.mapProvider || 'osm';
    if (provider === 'google') {
        return `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`;
    }
    return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=16/${lat}/${lng}`;
};

const decorateTripMarkers = (event) => {
    const comment = event.querySelector('.journal-comment');
    if (!comment) {
        return;
    }

    const paragraph = comment.querySelector('p') || comment;
    const html = paragraph.innerHTML;
    const brMatch = html.match(/<br\s*\/?>/i);
    const brIndex = brMatch ? html.indexOf(brMatch[0]) : -1;
    const firstLine = (brIndex === -1 ? html : html.slice(0, brIndex)).trim();

    const coords = firstLine.match(POI_LINE_RE);
    if (!coords) {
        return;
    }

    // Drop the machine line, keep the user's note (everything after the <br>).
    if (brIndex === -1) {
        paragraph.innerHTML = '';
    } else {
        paragraph.innerHTML = html.slice(brIndex + brMatch[0].length).replace(/^\s+/, '');
    }
    if (!comment.textContent.trim()) {
        comment.style.display = 'none';
    }

    const lat = parseFloat(coords[1]);
    const lng = parseFloat(coords[2]);
    const markers = event.querySelector('.trip-markers') || event;

    const pin = document.createElement('a');
    pin.className = 'trip-pin';
    pin.href = mapUrlFor(lat, lng);
    pin.target = '_blank';
    pin.rel = 'noopener';
    pin.textContent = `📍 ${lat.toFixed(2)}, ${lng.toFixed(2)}`;
    markers.appendChild(pin);
};

[...journalAddedEvents].forEach(decorateTripMarkers);

// Copy the public share link from the trip-detail share control. Delegated so
// it keeps working after HTMX swaps the control on share/unshare.
document.addEventListener('click', (e) => {
    const button = e.target.closest('.trip-share-copy');
    if (!button) {
        return;
    }

    navigator.clipboard.writeText(button.dataset.shareUrl).then(() => {
        const label = button.textContent;
        button.textContent = 'Copied';
        setTimeout(() => {
            button.textContent = label;
        }, 1500);
    });
});

// Called by the saved form's response: show the result for a moment, then
// close the form and bring its button back.
const onInlineFormSaved = (element, { button: buttonSelector, form: formSelector }) => {
    const closestJournalAdded = element.closest('.journal-added');

    const form = closestJournalAdded.querySelector(formSelector);
    const button = closestJournalAdded.querySelector(buttonSelector);
    const result = form.querySelector('.result-ok');

    setTimeout(() => {
        result.remove();

        form.classList.add('hidden');
        button.closest('.add-breakthrough').classList.remove('hidden');
        element.remove();
    }, 2000);
}

window.onBreakthroughAdded = (element) => onInlineFormSaved(element, INLINE_FORMS.breakthrough);
window.onJournalTagAdded = (element) => onInlineFormSaved(element, INLINE_FORMS.tag);

document.querySelectorAll('.breakthrough-outcome').forEach((outcome) => {
    const button = outcome.querySelector('button.accordion');
    const textareas = outcome.querySelectorAll('textarea');

    if (!button) {
        return;
    }

    button.addEventListener('click', (event) => {
        outcome.classList.toggle('open');
        event.stopPropagation();
        event.preventDefault();

        textareas.forEach(resizeTextarea);
    });

    const confidenceLevel = outcome.querySelector('.breakthrough-outcome-confidence input[type="range"]');
    const confidenceLevelValue = outcome.querySelector('.breakthrough-outcome-name .confidence-level');

    if (!confidenceLevel) {
        return;
    }

    confidenceLevel.addEventListener('input', () => {
        if (confidenceLevel.value === '0') {
            confidenceLevelValue.textContent = 'by';
        } else {
            confidenceLevelValue.textContent = `${confidenceLevel.value}%`;
        }
    });
});


const setUrlParameter = (parameter, value) => {
    const url = new URL(window.location.href);
    url.searchParams.set(parameter, value);
    window.location.href = url.toString();
}

window.setUrlParameter = setUrlParameter;

// Trip-detail code is loaded on demand: only the trip pages carry these
// selectors, so the Leaflet map (+ its CSS), the add-modal logic and the
// actions menu never ship on any other page. Each dynamic import() makes
// Rspack split the module into its own async chunk, fetched from the same
// /static/ publicPath as this bundle. Every one of them also self-guards
// internally, so the selector checks here only avoid a pointless request.
if (document.getElementById('trip-map')) {
    import(/* webpackChunkName: "trip_map" */ "./trip_map.js");
}
if (document.getElementById('trip-add-modal')) {
    import(/* webpackChunkName: "trip_add" */ "./trip_add.js");
}
if (document.querySelector('[data-trip-actions]')) {
    import(/* webpackChunkName: "trip_actions" */ "./trip_actions.js");
}
