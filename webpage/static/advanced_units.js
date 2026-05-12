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

        const selectedPanValue = panUnitByValue.has(select.value) ? select.value : "";
        panOptions.forEach((option) => option.remove());

        const advancedOption = buildOption(
            selectedPanValue || "__advanced_pan__",
            selectedPanValue ? panUnitByValue.get(selectedPanValue).label : "Advanced pan..."
        );
        advancedOption.dataset.advancedPanOption = "1";
        select.appendChild(advancedOption);

        const picker = document.createElement("div");
        picker.className = "advanced-unit-picker hidden";
        let isSyncingAdvancedSelection = false;

        const sizeSelect = document.createElement("select");
        sizeSelect.className = "advanced-unit-size";
        sizeSelect.setAttribute("aria-label", "Pan size");
        panSizes.forEach((size) => {
            sizeSelect.appendChild(buildOption(size.value, size.label));
        });

        const depthSelect = document.createElement("select");
        depthSelect.className = "advanced-unit-depth";
        depthSelect.setAttribute("aria-label", "Pan depth");

        picker.appendChild(sizeSelect);
        picker.appendChild(depthSelect);
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

        function syncAdvancedSelection() {
            const unit = selectedUnit();
            if (!unit) return;

            advancedOption.value = unit.value;
            advancedOption.textContent = unit.label;
            select.value = unit.value;
            picker.classList.remove("hidden");
            isSyncingAdvancedSelection = true;
            select.dispatchEvent(new Event("input", { bubbles: true }));
            select.dispatchEvent(new Event("change", { bubbles: true }));
            isSyncingAdvancedSelection = false;
        }

        function showPickerFromValue(unitValue) {
            const unit = panUnitByValue.get(unitValue) || panUnits[0];
            sizeSelect.value = unit.size;
            setDepthOptions(unit.size, unit.depth);
            syncAdvancedSelection();
        }

        select.addEventListener("change", () => {
            if (isSyncingAdvancedSelection) return;

            if (select.value === "__advanced_pan__") {
                showPickerFromValue("");
                return;
            }

            if (panUnitByValue.has(select.value)) {
                showPickerFromValue(select.value);
                return;
            }

            advancedOption.value = "__advanced_pan__";
            advancedOption.textContent = "Advanced pan...";
            picker.classList.add("hidden");
        });

        sizeSelect.addEventListener("change", () => {
            setDepthOptions(sizeSelect.value);
            syncAdvancedSelection();
        });
        depthSelect.addEventListener("change", syncAdvancedSelection);

        if (selectedPanValue) {
            showPickerFromValue(selectedPanValue);
        }
    };

    window.enhanceAdvancedUnitSelects = function enhanceAdvancedUnitSelects(scope = document) {
        scope.querySelectorAll("select").forEach(window.enhanceAdvancedUnitSelect);
    };

    window.enhanceAdvancedUnitSelects();
});
