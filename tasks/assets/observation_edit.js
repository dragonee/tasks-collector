// Single observation editor (/observations/<id>/): the collapsible History /
// Complex drawer, the Close / Save burger dropdowns, and the Complex panel's
// search / attach / detach behaviour.

const initObservationEdit = () => {
    const editor = document.querySelector(".observation-editor");
    if (!editor) {
        return;
    }

    const csrfToken = () => {
        const field = editor.querySelector("[name=csrfmiddlewaretoken]");
        return field ? field.value : "";
    };

    // --- Drawer: History / Complex toggle -------------------------------------
    const railButtons = [...editor.querySelectorAll(".drawer-rail [data-drawer]")];
    const panels = {
        history: editor.querySelector(".drawer-history"),
        complex: editor.querySelector(".drawer-complex"),
    };
    let currentDrawer = null;

    const setDrawer = (mode) => {
        // Clicking the active tab closes the drawer.
        currentDrawer = currentDrawer === mode ? null : mode;
        editor.classList.toggle("drawer-open", currentDrawer !== null);
        railButtons.forEach((btn) =>
            btn.classList.toggle("active", btn.dataset.drawer === currentDrawer)
        );
        Object.entries(panels).forEach(([key, panel]) => {
            if (panel) {
                panel.classList.toggle("shown", key === currentDrawer);
            }
        });
    };

    railButtons.forEach((btn) =>
        btn.addEventListener("click", () => setDrawer(btn.dataset.drawer))
    );

    // --- Topbar burger dropdowns (Close / Save extra actions) -----------------
    const menuToggles = [...editor.querySelectorAll(".burger[data-menu]")];

    const closeAllMenus = () => {
        editor.querySelectorAll(".action-menu").forEach((m) => (m.hidden = true));
    };

    menuToggles.forEach((toggle) => {
        toggle.addEventListener("click", (event) => {
            event.stopPropagation();
            const menu = editor.querySelector(`#${toggle.dataset.menu}`);
            if (!menu) {
                return;
            }
            const willOpen = menu.hidden;
            closeAllMenus();
            menu.hidden = !willOpen;
        });
    });

    document.addEventListener("click", (event) => {
        if (!event.target.closest(".split-action")) {
            closeAllMenus();
        }
    });

    // --- Complex panel: search / attach / detach ------------------------------
    const observationId = editor.dataset.observationId;
    if (!observationId) {
        return;
    }

    const searchInput = document.getElementById("observation-search");
    const searchResults = document.getElementById("search-results");

    const truncate = (text, length) =>
        text && text.length > length ? `${text.slice(0, length)}…` : text || "";

    const attachObservation = (otherId) => {
        fetch(`/observations/${observationId}/attach/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken(),
            },
            body: JSON.stringify({ other_observation_id: otherId }),
        })
            .then((response) => response.json())
            .then((data) => {
                if (data.id) {
                    window.location.reload();
                } else {
                    alert(`Error attaching observation: ${data.error || "Unknown error"}`);
                }
            })
            .catch((error) => {
                console.error("Attach error:", error);
                alert("Error attaching observation");
            });
    };

    const displaySearchResults = (results) => {
        if (!searchResults) {
            return;
        }
        const attachedStreamIds = [
            ...document.querySelectorAll(".attached-row"),
        ].map((el) => el.dataset.streamId);

        const html = (results || [])
            .filter(
                (obs) =>
                    String(obs.id) !== String(observationId) &&
                    !attachedStreamIds.includes(obs.event_stream_id)
            )
            .slice(0, 5)
            .map(
                (obs) => `
                <div class="search-result" data-obs-id="${obs.id}" data-stream-id="${obs.event_stream_id}">
                    <div class="result-situation"><strong>#${obs.id}:</strong> ${truncate(obs.situation, 100) || "No situation"}</div>
                    <div class="result-meta">${obs.pub_date} - ${obs.thread}</div>
                    <button type="button" class="attach-btn" data-obs-id="${obs.id}">Attach</button>
                </div>`
            )
            .join("");

        searchResults.innerHTML =
            html || '<div class="no-results">No matching observations</div>';
        searchResults.style.display = "block";

        searchResults.querySelectorAll(".attach-btn").forEach((btn) =>
            btn.addEventListener("click", () => attachObservation(btn.dataset.obsId))
        );
    };

    if (searchInput && searchResults) {
        let searchTimeout;
        searchInput.addEventListener("input", function () {
            const query = this.value.trim();
            clearTimeout(searchTimeout);

            if (query.length < 2) {
                searchResults.innerHTML = "";
                searchResults.style.display = "none";
                return;
            }

            searchTimeout = setTimeout(() => {
                fetch(
                    `/observations/search/?q=${encodeURIComponent(query)}&observation=${observationId}`
                )
                    .then((response) => response.json())
                    .then((data) => displaySearchResults(data.results || data))
                    .catch((error) => {
                        console.error("Search error:", error);
                        searchResults.innerHTML =
                            '<div class="search-error">Search error occurred</div>';
                        searchResults.style.display = "block";
                    });
            }, 300);
        });

        document.addEventListener("click", (event) => {
            if (!event.target.closest(".search-container")) {
                searchResults.style.display = "none";
            }
        });
    }

    // Detach (event delegation — the rows are server-rendered).
    document.addEventListener("click", (event) => {
        const btn = event.target.closest(".detach-btn");
        if (!btn) {
            return;
        }
        if (!confirm("Detach this observation?")) {
            return;
        }
        fetch(`/observations/${observationId}/detach/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken(),
            },
            body: JSON.stringify({ other_event_stream_id: btn.dataset.streamId }),
        })
            .then((response) => response.json())
            .then((data) => {
                if (data.id) {
                    window.location.reload();
                } else {
                    alert(`Error detaching observation: ${data.error || "Unknown error"}`);
                }
            })
            .catch((error) => {
                console.error("Detach error:", error);
                alert("Error detaching observation");
            });
    });
};

initObservationEdit();
