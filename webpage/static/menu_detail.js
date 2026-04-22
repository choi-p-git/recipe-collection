document.addEventListener("DOMContentLoaded", () => {
    const configForm = document.querySelector("[data-menu-bulk-config]");
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
