// Make textareas grow and shrink to fit their content.
//
// One shared ResizeObserver reacts to anything that changes a textarea's WIDTH
// — window resizes, layout shifts (e.g. the observation editor's History drawer
// squeezing the form column), and visibility toggles — while an input listener
// handles typing. The CSS min-height (or the textarea's `rows` attribute)
// provides the minimum size; the box itself never scrolls.

const tracked = new Set();
const lastWidth = new WeakMap();
let observer = null;

// Fit a textarea's height to its content. box-sizing is border-box app-wide
// (see styles/_general.scss), so the height must include the borders that
// scrollHeight omits; the content-box branch is kept for completeness.
const measure = (el) => {
    const cs = getComputedStyle(el);
    el.style.height = "auto";
    if (cs.boxSizing === "border-box") {
        const border =
            parseFloat(cs.borderTopWidth) + parseFloat(cs.borderBottomWidth);
        el.style.height = `${el.scrollHeight + border}px`;
    } else {
        const padding =
            parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
        el.style.height = `${el.scrollHeight - padding}px`;
    }
};

const onInput = (event) => measure(event.target);

const getObserver = () => {
    if (observer) {
        return observer;
    }
    observer = new ResizeObserver((entries) => {
        entries.forEach((entry) => {
            const el = entry.target;
            // Our own height writes also notify the observer; only re-fit when
            // the width (and therefore the text wrapping) actually changed, so
            // we never feed back into ourselves.
            if (lastWidth.get(el) === el.clientWidth) {
                return;
            }
            lastWidth.set(el, el.clientWidth);
            measure(el);
        });
    });
    return observer;
};

// Re-fit a textarea on demand (e.g. after a layout change JS triggers itself).
export const resizeTextarea = (el) => {
    if (el) {
        measure(el);
    }
};

export const attach = (el) => {
    if (!el || tracked.has(el)) {
        return;
    }
    tracked.add(el);
    el.classList.add("js-autosize");
    el.addEventListener("input", onInput);
    measure(el);
    lastWidth.set(el, el.clientWidth);
    getObserver().observe(el);
};

export const detach = (el) => {
    if (!el || !tracked.has(el)) {
        return;
    }
    tracked.delete(el);
    el.removeEventListener("input", onInput);
    el.classList.remove("js-autosize");
    if (observer) {
        observer.unobserve(el);
    }
};

// Attach to every textarea under `root` (the whole document by default).
export const autosizeAll = (root = document) => {
    root.querySelectorAll("textarea").forEach(attach);
};

// Web fonts load after the first measurement and reflow the text taller without
// changing the textarea width, so the ResizeObserver never sees it. Re-fit every
// tracked textarea once the fonts are ready (resolves immediately when cached).
if (typeof document !== "undefined" && document.fonts) {
    document.fonts.ready.then(() => tracked.forEach(measure));
}

// Vue 2 directive: <textarea v-autosize>. componentUpdated re-fits when the
// bound value changes from outside an input event (e.g. a form reset clearing
// v-model).
export const autosizeDirective = {
    inserted(el) {
        const ta = el.tagName === "TEXTAREA" ? el : el.querySelector("textarea");
        el._autosizeTarget = ta;
        attach(ta);
    },
    componentUpdated(el) {
        if (el._autosizeTarget) {
            measure(el._autosizeTarget);
        }
    },
    unbind(el) {
        detach(el._autosizeTarget);
    },
};
