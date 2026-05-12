document.addEventListener("DOMContentLoaded", () => {
    const configForm = document.querySelector("[data-menu-bulk-config]");
    const actionForm = document.querySelector("[data-menu-overview-action-form]");

    if (actionForm) {
        const actionSelect = actionForm.querySelector("[data-menu-overview-action-select]");
        if (actionSelect) {
            actionSelect.addEventListener("change", () => {
                const targetUrl = actionSelect.value;
                if (targetUrl) {
                    window.open(targetUrl, "_blank", "noopener");
                    actionSelect.value = "";
                }
            });
        }
        actionForm.addEventListener("submit", (event) => {
            event.preventDefault();
            const targetUrl = actionSelect ? actionSelect.value : "";
            if (targetUrl) {
                window.open(targetUrl, "_blank", "noopener");
                actionSelect.value = "";
            }
        });
    }

    if (!configForm) {
        return;
    }

    const actionSelect = configForm.querySelector("[data-bulk-action-select]");
    const scopeSelect = configForm.querySelector("[data-bulk-scope-select]");

    const submitConfig = () => {
        if (typeof configForm.requestSubmit === "function") {
            configForm.requestSubmit();
            return;
        }
        configForm.submit();
    };

    if (actionSelect) {
        actionSelect.addEventListener("change", submitConfig);
    }

    if (scopeSelect) {
        scopeSelect.addEventListener("change", submitConfig);
    }
});
