(() => {
    const DEFAULT_HOVER_OPEN_MS = 500;
    const DEFAULT_FETCH_INTENT_MS = 650;

    const popoverSelector = "[data-history-popover]";
    const triggerSelector = "[data-history-trigger]";
    const lazyPanelSelector = "[data-fetch-url]";
    const renderers = new Map();

    const closePopovers = (exceptPopover = null) => {
        document.querySelectorAll(`${popoverSelector}.is-open`).forEach((popover) => {
            if (popover !== exceptPopover) {
                popover.classList.remove("is-open");
                popover.dataset.pinned = "";
            }
        });
    };

    const renderLazyPanel = (panel, payload, popover) => {
        const rendererName = panel.dataset.popoverRenderer || popover.dataset.popoverRenderer || "";
        const renderer = renderers.get(rendererName);
        if (!renderer) {
            throw new Error(rendererName ? `Popover renderer '${rendererName}' was not registered.` : "Popover renderer was not configured.");
        }
        renderer(panel, payload, popover);
    };

    const loadLazyPanel = async (popover) => {
        const panel = popover.querySelector(lazyPanelSelector);
        if (!panel || panel.dataset.loaded === "true" || panel.dataset.loading === "true") {
            return;
        }
        panel.dataset.loading = "true";
        try {
            const response = await fetch(panel.dataset.fetchUrl || "", {headers: {"Accept": "application/json"}});
            const payload = await response.json();
            if (!response.ok || !payload.ok) {
                throw new Error(payload.error || "Unable to load popover.");
            }
            renderLazyPanel(panel, payload, popover);
            panel.dataset.loaded = "true";
        } catch (error) {
            panel.replaceChildren();
            const message = document.createElement("p");
            message.className = "muted";
            message.textContent = error.message || "Unable to load popover.";
            panel.appendChild(message);
        } finally {
            panel.dataset.loading = "";
        }
    };

    const initPopover = (popover) => {
        if (popover.dataset.popoverInitialized === "true") {
            return;
        }
        popover.dataset.popoverInitialized = "true";
        const trigger = popover.querySelector(triggerSelector);
        const lazyPanel = popover.querySelector(lazyPanelSelector);
        const hoverOpenMs = Number(popover.dataset.popoverHoverOpenMs || DEFAULT_HOVER_OPEN_MS);
        const fetchIntentMs = Number(popover.dataset.popoverFetchIntentMs || DEFAULT_FETCH_INTENT_MS);
        let hoverTimer = null;
        let fetchIntentTimer = null;

        const clearHoverTimer = () => {
            if (hoverTimer) {
                window.clearTimeout(hoverTimer);
                hoverTimer = null;
            }
        };

        const clearFetchIntentTimer = () => {
            if (fetchIntentTimer) {
                window.clearTimeout(fetchIntentTimer);
                fetchIntentTimer = null;
            }
        };

        const scheduleLazyFetch = () => {
            if (!lazyPanel) {
                return;
            }
            clearFetchIntentTimer();
            fetchIntentTimer = window.setTimeout(() => {
                fetchIntentTimer = null;
                loadLazyPanel(popover);
            }, fetchIntentMs);
        };

        const pinPopover = () => {
            closePopovers(popover);
            popover.classList.add("is-open");
            popover.dataset.pinned = "true";
        };

        popover.addEventListener("mouseenter", () => {
            clearHoverTimer();
            scheduleLazyFetch();
            hoverTimer = window.setTimeout(pinPopover, hoverOpenMs);
        });

        popover.addEventListener("mouseleave", () => {
            clearHoverTimer();
            clearFetchIntentTimer();
        });

        popover.addEventListener("focusin", () => {
            clearFetchIntentTimer();
            loadLazyPanel(popover);
        });

        trigger?.addEventListener("click", (event) => {
            if (trigger.tagName === "A") {
                return;
            }
            event.stopPropagation();
            const isPinned = popover.dataset.pinned === "true";
            closePopovers(popover);
            popover.classList.toggle("is-open", !isPinned);
            popover.dataset.pinned = isPinned ? "" : "true";
            if (!isPinned) {
                clearFetchIntentTimer();
                loadLazyPanel(popover);
            }
            if (isPinned) {
                trigger.blur();
            }
        });
    };

    const init = (root = document) => {
        root.querySelectorAll(popoverSelector).forEach(initPopover);
    };

    const registerRenderer = (name, renderer) => {
        if (!name || typeof renderer !== "function") {
            return;
        }
        renderers.set(name, renderer);
    };

    document.addEventListener("click", (event) => {
        if (!event.target.closest(popoverSelector)) {
            closePopovers();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closePopovers();
        }
    });

    window.AppPopover = {
        close: closePopovers,
        init,
        registerRenderer,
    };

    document.addEventListener("DOMContentLoaded", () => init());
})();
