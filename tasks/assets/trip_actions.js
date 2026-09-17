// Trip detail: the ⋮ menu next to the title and the "Stop trip" modal it opens.
//
// The modal's datetime-local is seeded with the current local time on every
// open, so "stop it now" is one extra click while a trip that really ended
// yesterday can be backdated. `min` is the trip's start and `max` is now —
// hints only; the server clamps a future value to now and rejects anything
// before the start.
//
// POST /trips/<id>/stop/ answers 204 and the page reloads: stopping rewrites
// the whole page (the add affordances go, the header gains an end date), so
// swapping a partial would not be enough.
//
// Loaded only for the owner of an active trip (see app.js).

import { bindTripModal } from './trip_modal.js';

function csrfToken() {
    const el = document.body.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
}

// <input type="datetime-local"> speaks naive local time; toISOString() is UTC,
// so shift by the zone offset before slicing off the seconds and the trailing Z.
function localInputValue(date) {
    const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return shifted.toISOString().slice(0, 16);
}

const modal = document.getElementById('trip-stop-modal');
const actions = document.querySelector('[data-trip-actions]');

if (modal) {
    const storyId = modal.dataset.storyId;
    const form = modal.querySelector('.trip-stop-form');
    const input = form.querySelector('input[name=stopped]');
    const status = form.querySelector('.trip-modal-status');
    const submit = form.querySelector('.trip-modal-submit');

    function setStatus(text, isError) {
        status.textContent = text || '';
        status.classList.toggle('is-error', Boolean(isError));
    }

    const { open: openModal } = bindTripModal(modal, {
        closeSelector: '[data-trip-stop-close]',
        onOpen: () => {
            const now = localInputValue(new Date());
            input.value = now;
            input.max = now;
            input.min = modal.dataset.started || '';
            setStatus('');
        },
    });

    document.querySelectorAll('[data-trip-stop-open]').forEach((btn) => {
        btn.addEventListener('click', openModal);
    });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        submit.disabled = true;
        setStatus('Stopping…');
        try {
            const res = await fetch(`/trips/${storyId}/stop/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': csrfToken(),
                },
                body: new URLSearchParams({ stopped: input.value }).toString(),
            });
            if (!res.ok) {
                // The stop view answers 4xx with a plain-text reason
                // ("stop time is before the trip started"); show it as-is.
                throw new Error((await res.text()) || `stop failed (${res.status})`);
            }
            // Leave the button disabled: the reload replaces the page anyway.
            window.location.reload();
        } catch (err) {
            setStatus(err.message || 'Something went wrong.', true);
            submit.disabled = false;
        }
    });
}

if (actions) {
    const toggle = actions.querySelector('.trip-actions-toggle');
    const menu = actions.querySelector('.trip-actions-menu');

    function setMenuOpen(open) {
        menu.hidden = !open;
        toggle.setAttribute('aria-expanded', String(open));
    }

    toggle.addEventListener('click', (e) => {
        // Without this the document listener below would see the same click
        // and immediately close the menu again.
        e.stopPropagation();
        setMenuOpen(menu.hidden);
    });

    // Picking an item acts through its own handler; closing here keeps the
    // menu from lingering over whatever it opened.
    menu.addEventListener('click', () => setMenuOpen(false));

    document.addEventListener('click', (e) => {
        if (!menu.hidden && !actions.contains(e.target)) {
            setMenuOpen(false);
        }
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !menu.hidden) {
            setMenuOpen(false);
        }
    });
}
