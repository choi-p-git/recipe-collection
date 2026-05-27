(function () {
    const delayMs = 250;
    const indicator = document.querySelector("[data-app-loading-indicator]");

    if (!indicator) {
        return;
    }

    const originalFetch = typeof window.fetch === "function" ? window.fetch.bind(window) : null;
    let activeRequestCount = 0;
    let visibleRequestCount = 0;
    let navigationTimerId = null;

    function setIndicatorVisible(isVisible) {
        indicator.hidden = !isVisible;
        indicator.setAttribute("aria-hidden", isVisible ? "false" : "true");
    }

    function updateIndicator() {
        setIndicatorVisible(visibleRequestCount > 0);
    }

    function showIndicator() {
        visibleRequestCount += 1;
        updateIndicator();
    }

    function hideIndicator() {
        visibleRequestCount = Math.max(0, visibleRequestCount - 1);
        updateIndicator();
    }

    function scheduleNavigationIndicator() {
        if (navigationTimerId !== null) {
            return;
        }
        navigationTimerId = window.setTimeout(function () {
            navigationTimerId = null;
            showIndicator();
        }, delayMs);
    }

    function clearNavigationIndicator() {
        if (navigationTimerId !== null) {
            window.clearTimeout(navigationTimerId);
            navigationTimerId = null;
        }
        setIndicatorVisible(false);
        visibleRequestCount = 0;
    }

    function runAfterPaint(callback) {
        window.requestAnimationFrame(function () {
            window.setTimeout(callback, 0);
        });
    }

    function isPlainSameWindowNavigation(event, link) {
        if (
            event.defaultPrevented
            || event.button !== 0
            || event.metaKey
            || event.ctrlKey
            || event.shiftKey
            || event.altKey
            || link.target
            || link.hasAttribute("download")
        ) {
            return false;
        }
        const nextUrl = new URL(link.href, window.location.href);
        return (
            nextUrl.origin === window.location.origin
            && !(nextUrl.pathname === window.location.pathname && nextUrl.search === window.location.search && nextUrl.hash)
        );
    }

    function submitFormAfterPaint(form, submitter) {
        form.dataset.appLoadingNavigationSubmit = "true";
        runAfterPaint(function () {
            if (submitter && typeof form.requestSubmit === "function") {
                form.requestSubmit(submitter);
                return;
            }
            HTMLFormElement.prototype.submit.call(form);
        });
    }

    function isPlainSameWindowFormSubmission(event, form) {
        if (
            event.defaultPrevented
            || form.dataset.appLoadingNavigationSubmit === "true"
            || form.method.toLowerCase() === "dialog"
            || form.target
        ) {
            return false;
        }
        const submitter = event.submitter;
        if (submitter && submitter.getAttribute("formtarget")) {
            return false;
        }
        const action = submitter && submitter.getAttribute("formaction")
            ? submitter.getAttribute("formaction")
            : form.action;
        return new URL(action || window.location.href, window.location.href).origin === window.location.origin;
    }

    document.addEventListener("click", function (event) {
        const link = event.target.closest("a[href]");
        if (!link || !isPlainSameWindowNavigation(event, link)) {
            return;
        }
        scheduleNavigationIndicator();
        event.preventDefault();
        runAfterPaint(function () {
            window.location.assign(link.href);
        });
    });

    document.addEventListener("submit", function (event) {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || !isPlainSameWindowFormSubmission(event, form)) {
            return;
        }
        scheduleNavigationIndicator();
        event.preventDefault();
        submitFormAfterPaint(form, event.submitter);
    });

    window.addEventListener("pageshow", clearNavigationIndicator);

    window.fetch = function appFetchWithLoadingIndicator(input, init) {
        if (!originalFetch) {
            throw new TypeError("Fetch is not available in this browser.");
        }
        activeRequestCount += 1;
        let didShow = false;
        const timerId = window.setTimeout(function () {
            if (activeRequestCount <= 0) {
                return;
            }
            didShow = true;
            showIndicator();
        }, delayMs);

        return originalFetch(input, init).finally(function () {
            activeRequestCount = Math.max(0, activeRequestCount - 1);
            window.clearTimeout(timerId);
            if (didShow) {
                hideIndicator();
            }
        });
    };
})();
