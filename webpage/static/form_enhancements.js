document.addEventListener("DOMContentLoaded", () => {
    const selectableTypes = new Set([
        "date",
        "email",
        "number",
        "password",
        "search",
        "tel",
        "text",
        "time",
        "url",
    ]);

    const shouldAutoSelect = (field) => {
        if (field.dataset.noAutoSelect === "true") {
            return false;
        }
        if (field.tagName === "TEXTAREA") {
            return true;
        }
        if (field.tagName !== "INPUT") {
            return false;
        }
        return selectableTypes.has((field.getAttribute("type") || "text").toLowerCase());
    };

    document.addEventListener("focusin", (event) => {
        const field = event.target;
        if (!field || !shouldAutoSelect(field) || field.readOnly || field.disabled) {
            return;
        }

        window.requestAnimationFrame(() => {
            try {
                field.select();
            } catch {
                // Some browser-native controls expose select() inconsistently.
            }
        });
    });
});
