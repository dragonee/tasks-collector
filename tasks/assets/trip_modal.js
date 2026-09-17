// Shared show/hide plumbing for the trip-detail modals (add note/photo in
// trip_add.js, stop trip in trip_actions.js). Each modal keeps its own form
// and submit logic; only the overlay behaviour lives here.

const OPEN_CLASS = 'trip-modal-open';

/**
 * Wire a `.trip-modal` overlay: it closes on any element matching
 * `closeSelector` (the backdrop and the Cancel button), and on Escape while
 * it is visible. `onOpen`/`onClose` are for the caller's own bookkeeping —
 * seeding a field, resetting the form.
 *
 * Returns the `open`/`close` pair so the caller can drive it from its own
 * triggers.
 */
export function bindTripModal(modal, { closeSelector, onOpen, onClose } = {}) {
    function open() {
        modal.hidden = false;
        document.body.classList.add(OPEN_CLASS);
        if (onOpen) {
            onOpen();
        }
    }

    function close() {
        modal.hidden = true;
        document.body.classList.remove(OPEN_CLASS);
        if (onClose) {
            onClose();
        }
    }

    if (closeSelector) {
        modal.querySelectorAll(closeSelector).forEach((el) => {
            el.addEventListener('click', close);
        });
    }
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !modal.hidden) {
            close();
        }
    });

    return { open, close };
}
