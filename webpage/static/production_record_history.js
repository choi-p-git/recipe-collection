document.addEventListener("DOMContentLoaded", () => {
    const HISTORY_HOVER_FOCUS_MS = 500;

    const closeHistoryPopovers = (exceptPopover = null) => {
        document.querySelectorAll("[data-history-popover].is-open").forEach((popover) => {
            if (popover !== exceptPopover) {
                popover.classList.remove("is-open");
                popover.dataset.pinned = "";
            }
        });
    };

    document.querySelectorAll("[data-history-popover]").forEach((popover) => {
        const trigger = popover.querySelector("[data-history-trigger]");
        let hoverTimer = null;

        const pinPopover = () => {
            closeHistoryPopovers(popover);
            popover.classList.add("is-open");
            popover.dataset.pinned = "true";
        };

        const clearHoverTimer = () => {
            if (hoverTimer) {
                window.clearTimeout(hoverTimer);
                hoverTimer = null;
            }
        };

        popover.addEventListener("mouseenter", () => {
            clearHoverTimer();
            hoverTimer = window.setTimeout(pinPopover, HISTORY_HOVER_FOCUS_MS);
        });

        popover.addEventListener("mouseleave", () => {
            clearHoverTimer();
        });

        trigger?.addEventListener("click", (event) => {
            event.stopPropagation();
            const isPinned = popover.dataset.pinned === "true";
            closeHistoryPopovers(popover);
            popover.classList.toggle("is-open", !isPinned);
            popover.dataset.pinned = isPinned ? "" : "true";
            if (isPinned) {
                trigger.blur();
            }
        });
    });

    document.addEventListener("click", (event) => {
        if (!event.target.closest("[data-history-popover]")) {
            closeHistoryPopovers();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeHistoryPopovers();
        }
    });
});
