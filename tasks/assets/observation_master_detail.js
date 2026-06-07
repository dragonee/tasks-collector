// Master-detail interaction for the Observations pages (live / closed /
// insights). The left column lists situations; clicking one reveals its full
// detail panel in the right column — like selecting a message in an email
// client. The first situation is selected on load (or, in attach mode, the base
// observation the others are being attached to).

const initObservationMasterDetail = () => {
    const layout = document.querySelector(".observations-layout");
    if (!layout) {
        return;
    }

    const left = layout.querySelector(".split-left");
    const right = layout.querySelector(".split-right");
    if (!left || !right) {
        return;
    }

    const items = [...left.querySelectorAll(".situation-item[data-obs]")];
    const panels = [...right.querySelectorAll(".observation-detail[data-obs]")];
    const empty = right.querySelector(".detail-empty");

    if (panels.length === 0) {
        return;
    }

    const select = (obs) => {
        let matched = false;
        items.forEach((item) =>
            item.classList.toggle("selected", item.dataset.obs === obs)
        );
        panels.forEach((panel) => {
            const show = panel.dataset.obs === obs;
            panel.classList.toggle("shown", show);
            if (show) {
                matched = true;
            }
        });
        if (empty) {
            empty.style.display = matched ? "none" : "";
        }
    };

    items.forEach((item) => {
        item.addEventListener("click", (event) => {
            // Leave the attach checkbox and any inline links to their own handlers.
            if (event.target.closest("a, input, label")) {
                return;
            }
            select(item.dataset.obs);
        });
    });

    // Initial selection: the attach-mode base observation, otherwise the first.
    const base = layout.dataset.baseObs;
    if (base) {
        select(base);
    } else if (items.length) {
        select(items[0].dataset.obs);
    }
};

initObservationMasterDetail();
