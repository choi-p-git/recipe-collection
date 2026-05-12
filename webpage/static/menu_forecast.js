document.addEventListener("DOMContentLoaded", () => {
    const controls = Array.from(document.querySelectorAll("[data-forecast-control]"));
    const saveState = new Map();
    const SAVE_DEBOUNCE_MS = 500;

    const setStatus = (control, state, message) => {
        const status = control.querySelector("[data-forecast-status]");
        if (!status) {
            return;
        }
        status.textContent = message;
        status.dataset.state = state;
    };

    const hasUnsyncedChanges = () => {
        for (const state of saveState.values()) {
            if (state === "dirty" || state === "saving" || state === "error") {
                return true;
            }
        }
        return false;
    };

    const saveForecast = async (control) => {
        const quantityInput = control.querySelector("[data-forecast-quantity]");
        const unitSelect = control.querySelector("[data-forecast-unit]");
        const saveUrl = control.dataset.saveUrl;
        if (!quantityInput || !unitSelect || !saveUrl) {
            return;
        }

        saveState.set(saveUrl, "saving");
        setStatus(control, "saving", "Saving...");

        try {
            const response = await fetch(saveUrl, {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    forecast_yield_quantity: quantityInput.value,
                    forecast_yield_unit: unitSelect.value,
                }),
            });
            const payload = await response.json();
            if (!response.ok || !payload.ok) {
                throw new Error(payload.error || "Unable to save forecast.");
            }
            saveState.set(saveUrl, "saved");
            setStatus(control, "saved", "✓ Saved");
        } catch (error) {
            saveState.set(saveUrl, "error");
            setStatus(control, "error", error.message || "Save failed");
        }
    };

    const scheduleSave = (control) => {
        const saveUrl = control.dataset.saveUrl;
        const previousTimer = control.dataset.saveTimer;
        if (previousTimer) {
            window.clearTimeout(Number(previousTimer));
        }
        saveState.set(saveUrl, "dirty");
        setStatus(control, "dirty", "Unsaved");
        const timer = window.setTimeout(() => {
            saveForecast(control);
        }, SAVE_DEBOUNCE_MS);
        control.dataset.saveTimer = String(timer);
    };

    controls.forEach((control) => {
        const quantityInput = control.querySelector("[data-forecast-quantity]");
        const unitSelect = control.querySelector("[data-forecast-unit]");
        if (!quantityInput || !unitSelect) {
            return;
        }
        quantityInput.addEventListener("input", () => scheduleSave(control));
        unitSelect.addEventListener("change", () => scheduleSave(control));
    });

    window.addEventListener("beforeunload", (event) => {
        if (!hasUnsyncedChanges()) {
            return;
        }
        event.preventDefault();
        event.returnValue = "";
    });
});
