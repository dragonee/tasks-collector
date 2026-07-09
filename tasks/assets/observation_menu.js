// Lower-pane controls for the Observations pages: Folder (navigates between the
// Mine / All / Closed / Insights list URLs), Type (an ephemeral ?type= filter)
// and Sort (a ?sort= ordering persisted to localStorage so the chosen order
// carries across visits). The server does the actual filtering and ordering;
// this only rewrites the URL on change and re-applies the saved sort on load.

const SORT_KEY = "observations.sort";
const DEFAULT_SORT = "added";

const initObservationMenu = () => {
    const menu = document.querySelector("[data-observation-menu]");
    if (!menu) {
        return;
    }

    const folderSelect = menu.querySelector(".folder-select");
    const typeSelect = menu.querySelector(".type-select");
    const sortSelect = menu.querySelector(".sort-select");

    const url = new URL(window.location.href);
    const urlSort = url.searchParams.get("sort");
    const storedSort = localStorage.getItem(SORT_KEY);

    // Persist an explicit ?sort= choice; otherwise re-apply a saved non-default
    // one by redirecting once (no loop: after the replace, ?sort= is present).
    if (urlSort) {
        if (storedSort !== urlSort) {
            localStorage.setItem(SORT_KEY, urlSort);
        }
    } else if (storedSort && storedSort !== DEFAULT_SORT) {
        url.searchParams.set("sort", storedSort);
        window.location.replace(url.toString());
        return;
    }

    // Navigate to `target` after (optionally) syncing the current sort onto it.
    const go = (target, { keepSort }) => {
        if (keepSort) {
            const sort = sortSelect ? sortSelect.value : urlSort || storedSort;
            if (sort && sort !== DEFAULT_SORT) {
                target.searchParams.set("sort", sort);
            } else {
                target.searchParams.delete("sort");
            }
        }
        window.location.href = target.toString();
    };

    // Folder: jump to the selected list URL, carrying the current sort but
    // dropping the ephemeral type filter (each folder opens at Type = All).
    if (folderSelect) {
        folderSelect.addEventListener("change", () => {
            const target = new URL(folderSelect.value, window.location.origin);
            go(target, { keepSort: true });
        });
    }

    // Type: ephemeral — reflected only in the URL, never stored.
    if (typeSelect) {
        typeSelect.addEventListener("change", () => {
            const target = new URL(window.location.href);
            if (typeSelect.value) {
                target.searchParams.set("type", typeSelect.value);
            } else {
                target.searchParams.delete("type");
            }
            window.location.href = target.toString();
        });
    }

    // Sort: persisted to localStorage and reflected in the URL.
    if (sortSelect) {
        sortSelect.addEventListener("change", () => {
            localStorage.setItem(SORT_KEY, sortSelect.value);
            const target = new URL(window.location.href);
            go(target, { keepSort: true });
        });
    }
};

initObservationMenu();
