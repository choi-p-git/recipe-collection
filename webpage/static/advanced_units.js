document.addEventListener("DOMContentLoaded", () => {
    const config = window.recipeAdvancedUnitOptions || {};
    const panUnits = config.units || [];
    const panSizes = config.sizes || [];
    const panDepths = config.depths || [];

    if (!panUnits.length) return;

    const panUnitByValue = new Map(panUnits.map((unit) => [unit.value, unit]));
    const unitsBySize = new Map();
    panUnits.forEach((unit) => {
        if (!unitsBySize.has(unit.size)) {
            unitsBySize.set(unit.size, []);
        }
        unitsBySize.get(unit.size).push(unit);
    });

    function buildOption(value, label) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        return option;
    }

    window.enhanceAdvancedUnitSelect = function enhanceUnitSelect(select) {
        if (select.dataset.advancedUnitsEnhanced === "1") return;

        const panOptions = Array.from(select.options).filter((option) => panUnitByValue.has(option.value));
        if (!panOptions.length) return;

        select.dataset.advancedUnitsEnhanced = "1";

        let committedPanValue = panUnitByValue.has(select.value) ? select.value : "";
        let previousSelectValue = committedPanValue || select.value;
        panOptions.forEach((option) => option.remove());

        const advancedOption = buildOption(
            committedPanValue || "__advanced_pan__",
            committedPanValue ? panUnitByValue.get(committedPanValue).label : "Advanced pan..."
        );
        advancedOption.dataset.advancedPanOption = "1";
        select.appendChild(advancedOption);
        if (committedPanValue) {
            select.value = committedPanValue;
        }

        const picker = document.createElement("div");
        picker.className = "advanced-unit-picker hidden";

        const trigger = document.createElement("button");
        trigger.type = "button";
        trigger.className = "advanced-unit-trigger";
        trigger.textContent = "...";
        trigger.title = "Advanced pan size";

        const overlay = document.createElement("div");
        overlay.className = "advanced-unit-overlay hidden";

        const title = document.createElement("div");
        title.className = "advanced-unit-overlay-title";
        title.textContent = "Pan size";

        const sizeSelect = document.createElement("select");
        sizeSelect.className = "advanced-unit-size";
        sizeSelect.setAttribute("aria-label", "Pan size");
        panSizes.forEach((size) => {
            sizeSelect.appendChild(buildOption(size.value, size.label));
        });

        const depthSelect = document.createElement("select");
        depthSelect.className = "advanced-unit-depth";
        depthSelect.setAttribute("aria-label", "Pan depth");

        const actions = document.createElement("div");
        actions.className = "advanced-unit-actions";

        const applyButton = document.createElement("button");
        applyButton.type = "button";
        applyButton.className = "button-compact";
        applyButton.textContent = "Apply";

        const cancelButton = document.createElement("button");
        cancelButton.type = "button";
        cancelButton.className = "button-secondary button-compact";
        cancelButton.textContent = "Cancel";

        actions.appendChild(applyButton);
        actions.appendChild(cancelButton);
        overlay.appendChild(title);
        overlay.appendChild(sizeSelect);
        overlay.appendChild(depthSelect);
        overlay.appendChild(actions);
        picker.appendChild(trigger);
        picker.appendChild(overlay);
        select.insertAdjacentElement("afterend", picker);

        function setDepthOptions(sizeValue, selectedDepth = "") {
            depthSelect.innerHTML = "";
            const availableDepths = new Set((unitsBySize.get(sizeValue) || []).map((unit) => unit.depth));
            panDepths.forEach((depth) => {
                const option = buildOption(depth.value, depth.label);
                option.disabled = !availableDepths.has(depth.value);
                depthSelect.appendChild(option);
            });

            const nextDepth = selectedDepth && availableDepths.has(selectedDepth)
                ? selectedDepth
                : (unitsBySize.get(sizeValue) || [])[0]?.depth || "";
            depthSelect.value = nextDepth;
        }

        function selectedUnit() {
            return panUnits.find((unit) => unit.size === sizeSelect.value && unit.depth === depthSelect.value);
        }

        function setOverlayFromValue(unitValue) {
            const unit = panUnitByValue.get(unitValue) || panUnits[0];
            sizeSelect.value = unit.size;
            setDepthOptions(unit.size, unit.depth);
        }

        function openOverlay(unitValue = committedPanValue) {
            setOverlayFromValue(unitValue);
            picker.classList.remove("hidden");
            overlay.classList.remove("hidden");
            trigger.setAttribute("aria-expanded", "true");
            sizeSelect.focus();
        }

        function closeOverlay() {
            overlay.classList.add("hidden");
            trigger.setAttribute("aria-expanded", "false");
        }

        function commitPanUnit(unit) {
            if (!unit) return;
            committedPanValue = unit.value;
            previousSelectValue = unit.value;
            advancedOption.value = unit.value;
            advancedOption.textContent = unit.label;
            trigger.textContent = "...";
            picker.classList.remove("hidden");
            closeOverlay();
            select.value = unit.value;
            select.dispatchEvent(new Event("input", { bubbles: true }));
            select.dispatchEvent(new Event("change", { bubbles: true }));
        }

        function cancelSelection() {
            closeOverlay();
            if (!committedPanValue && select.value === "__advanced_pan__") {
                select.value = previousSelectValue && previousSelectValue !== "__advanced_pan__"
                    ? previousSelectValue
                    : Array.from(select.options).find((option) => option.value !== "__advanced_pan__")?.value || "";
                picker.classList.add("hidden");
                select.dispatchEvent(new Event("change", { bubbles: true }));
            }
        }

        select.addEventListener("focus", () => {
            previousSelectValue = select.value;
        });

        select.addEventListener("change", () => {
            if (select.value === "__advanced_pan__") {
                picker.classList.remove("hidden");
                openOverlay(committedPanValue);
                return;
            }

            if (panUnitByValue.has(select.value)) {
                committedPanValue = select.value;
                const unit = panUnitByValue.get(select.value);
                advancedOption.value = unit.value;
                advancedOption.textContent = unit.label;
                trigger.textContent = "...";
                picker.classList.remove("hidden");
                closeOverlay();
                return;
            }

            advancedOption.value = "__advanced_pan__";
            advancedOption.textContent = "Advanced pan...";
            trigger.textContent = "...";
            committedPanValue = "";
            picker.classList.add("hidden");
            closeOverlay();
        });

        sizeSelect.addEventListener("change", () => {
            setDepthOptions(sizeSelect.value);
        });

        trigger.addEventListener("click", () => {
            if (overlay.classList.contains("hidden")) {
                openOverlay(committedPanValue);
            } else {
                closeOverlay();
            }
        });

        applyButton.addEventListener("click", () => {
            commitPanUnit(selectedUnit());
        });

        cancelButton.addEventListener("click", cancelSelection);

        document.addEventListener("click", (event) => {
            if (!picker.contains(event.target) && event.target !== select) {
                closeOverlay();
            }
        });

        if (committedPanValue) {
            setOverlayFromValue(committedPanValue);
            picker.classList.remove("hidden");
            trigger.setAttribute("aria-expanded", "false");
        }
    };

    window.enhanceAdvancedUnitSelects = function enhanceAdvancedUnitSelects(scope = document) {
        scope.querySelectorAll("select").forEach(window.enhanceAdvancedUnitSelect);
    };

    window.enhanceAdvancedUnitSelects();
});
