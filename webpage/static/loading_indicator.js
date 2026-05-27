(function () {
    const delayMs = 250;
    const indicator = document.querySelector("[data-app-loading-indicator]");

    if (!indicator || typeof window.fetch !== "function") {
        return;
    }

    const originalFetch = window.fetch.bind(window);
    let activeRequestCount = 0;
    let visibleRequestCount = 0;

    function setIndicatorVisible(isVisible) {
        indicator.hidden = !isVisible;
        indicator.setAttribute("aria-hidden", isVisible ? "false" : "true");
    }

    function updateIndicator() {
        setIndicatorVisible(visibleRequestCount > 0);
    }

    window.fetch = function appFetchWithLoadingIndicator(input, init) {
        activeRequestCount += 1;
        let didShow = false;
        const timerId = window.setTimeout(function () {
            if (activeRequestCount <= 0) {
                return;
            }
            didShow = true;
            visibleRequestCount += 1;
            updateIndicator();
        }, delayMs);

        return originalFetch(input, init).finally(function () {
            activeRequestCount = Math.max(0, activeRequestCount - 1);
            window.clearTimeout(timerId);
            if (didShow) {
                visibleRequestCount = Math.max(0, visibleRequestCount - 1);
                updateIndicator();
            }
        });
    };
})();
