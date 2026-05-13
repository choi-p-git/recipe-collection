document.addEventListener("DOMContentLoaded", () => {
    const controls = Array.from(document.querySelectorAll("[data-forecast-control]"));
    const saveState = new Map();
    const SAVE_DEBOUNCE_MS = 500;
    const unitProfiles = new Map(
        (window.recipeUnitMeasurementOptions || []).map((unit) => [unit.unit, unit])
    );

    const formatNumber = (quantity) => {
        const rounded = Math.round(quantity * 1000) / 1000;
        if (rounded < 0.001) return "according to taste";
        return String(Number(rounded.toPrecision(12)));
    };

    const convertUnit = (quantity, fromUnit, toUnit) => {
        const source = unitProfiles.get(fromUnit);
        const target = unitProfiles.get(toUnit);
        if (!source || !target) return null;
        if (source.measurement_type !== target.measurement_type) return null;
        if (source.canonical_unit !== target.canonical_unit) return null;
        return Number(quantity) * Number(source.canonical_factor) / Number(target.canonical_factor);
    };

    const bridgeMassVolume = (quantity, fromUnit, toUnit, data) => {
        const source = unitProfiles.get(fromUnit);
        const target = unitProfiles.get(toUnit);
        const mass = unitProfiles.get(data.massUnit);
        const volume = unitProfiles.get(data.volumeUnit);
        if (!source || !target || !mass || !volume) return null;
        if (!["mass", "volume"].includes(source.measurement_type)) return null;
        if (!["mass", "volume"].includes(target.measurement_type)) return null;
        if (source.measurement_type === target.measurement_type) return null;
        if (mass.measurement_type !== "mass" || volume.measurement_type !== "volume") return null;
        if (!data.massQuantity || !data.volumeQuantity) return null;

        const sourceCanonical = Number(quantity) * Number(source.canonical_factor);
        const massCanonical = Number(data.massQuantity) * Number(mass.canonical_factor);
        const volumeCanonical = Number(data.volumeQuantity) * Number(volume.canonical_factor);
        if (massCanonical <= 0 || volumeCanonical <= 0) return null;

        const targetCanonical = source.measurement_type === "mass"
            ? sourceCanonical * volumeCanonical / massCanonical
            : sourceCanonical * massCanonical / volumeCanonical;
        return targetCanonical / Number(target.canonical_factor);
    };

    const readRecipeData = (control) => ({
        yieldQuantity: Number(control.dataset.recipeYieldQuantity || 0),
        yieldUnit: control.dataset.recipeYieldUnit || "",
        massQuantity: Number(control.dataset.recipeMassQuantity || 0),
        massUnit: control.dataset.recipeMassUnit || "",
        volumeQuantity: Number(control.dataset.recipeVolumeQuantity || 0),
        volumeUnit: control.dataset.recipeVolumeUnit || "",
        servingSizeQuantity: Number(control.dataset.recipeServingSizeQuantity || 0),
        servingSizeUnit: control.dataset.recipeServingSizeUnit || "",
    });

    const calculatePortions = (control) => {
        const row = control.closest("tr");
        const quantityInput = control.querySelector("[data-forecast-quantity]");
        const unitSelect = control.querySelector("[data-forecast-unit]");
        const servingQuantityInput = row?.querySelector("[data-user-serving-quantity]");
        const servingUnitSelect = row?.querySelector("[data-user-serving-unit]");
        const result = row?.querySelector("[data-user-serving-result]");
        if (!quantityInput || !unitSelect || !servingQuantityInput || !servingUnitSelect || !result) {
            return;
        }

        const forecastQuantity = Number(quantityInput.value);
        const forecastUnit = unitSelect.value;
        const servingQuantity = Number(servingQuantityInput.value);
        const servingUnit = servingUnitSelect.value;
        if (!forecastQuantity || forecastQuantity < 0 || !forecastUnit || !servingQuantity || servingQuantity <= 0 || !servingUnit) {
            result.textContent = "--";
            return;
        }

        const recipeData = readRecipeData(control);
        let servingTotal = convertUnit(forecastQuantity, forecastUnit, servingUnit);
        if (servingTotal === null) {
            const forecastInRecipeYield = convertUnit(forecastQuantity, forecastUnit, recipeData.yieldUnit);
            const scaleFactor = forecastInRecipeYield !== null && recipeData.yieldQuantity > 0
                ? forecastInRecipeYield / recipeData.yieldQuantity
                : null;
            const servingProfile = unitProfiles.get(servingUnit);
            if (scaleFactor !== null && servingProfile) {
                let basisQuantity = null;
                let basisUnit = null;
                if (servingProfile.measurement_type === "mass") {
                    basisQuantity = recipeData.massQuantity;
                    basisUnit = recipeData.massUnit;
                } else if (servingProfile.measurement_type === "volume") {
                    basisQuantity = recipeData.volumeQuantity;
                    basisUnit = recipeData.volumeUnit;
                } else if (servingProfile.measurement_type === "count") {
                    basisQuantity = recipeData.yieldQuantity;
                    basisUnit = recipeData.yieldUnit;
                }
                if (basisQuantity && basisUnit) {
                    servingTotal = convertUnit(basisQuantity * scaleFactor, basisUnit, servingUnit);
                }
            }
        }
        if (servingTotal === null) {
            servingTotal = bridgeMassVolume(forecastQuantity, forecastUnit, servingUnit, recipeData);
        }
        result.textContent = servingTotal === null
            ? "Unavailable"
            : `${formatNumber(servingTotal / servingQuantity)} portions`;
    };

    const calculateServingTotal = (servingQuantity, servingUnit, recipeData) => {
        if (!servingQuantity || servingQuantity <= 0 || !servingUnit) {
            return null;
        }

        const servingProfile = unitProfiles.get(servingUnit);
        if (!servingProfile) {
            return null;
        }

        const directYieldTotal = convertUnit(recipeData.yieldQuantity, recipeData.yieldUnit, servingUnit);
        if (directYieldTotal !== null) {
            return directYieldTotal;
        }

        let basisQuantity = null;
        let basisUnit = null;
        if (servingProfile.measurement_type === "mass") {
            basisQuantity = recipeData.massQuantity;
            basisUnit = recipeData.massUnit;
        } else if (servingProfile.measurement_type === "volume") {
            basisQuantity = recipeData.volumeQuantity;
            basisUnit = recipeData.volumeUnit;
        } else if (servingProfile.measurement_type === "count") {
            basisQuantity = recipeData.yieldQuantity;
            basisUnit = recipeData.yieldUnit;
        }

        if (!basisQuantity || !basisUnit) {
            return null;
        }

        return convertUnit(basisQuantity, basisUnit, servingUnit);
    };

    const scaleToDesiredPortions = (control) => {
        const row = control.closest("tr");
        const quantityInput = control.querySelector("[data-forecast-quantity]");
        const unitSelect = control.querySelector("[data-forecast-unit]");
        const servingQuantityInput = row?.querySelector("[data-user-serving-quantity]");
        const servingUnitSelect = row?.querySelector("[data-user-serving-unit]");
        const desiredPortionsInput = row?.querySelector("[data-desired-portions]");
        if (!quantityInput || !unitSelect || !servingQuantityInput || !servingUnitSelect || !desiredPortionsInput) {
            return;
        }

        const recipeData = readRecipeData(control);
        const desiredPortions = Number(desiredPortionsInput.value);
        const servingQuantity = Number(servingQuantityInput.value || recipeData.servingSizeQuantity);
        const servingUnit = servingUnitSelect.value || recipeData.servingSizeUnit;
        if (!desiredPortions || desiredPortions <= 0 || !servingQuantity || servingQuantity <= 0 || !servingUnit) {
            setStatus(control, "error", "Portions and serving size required");
            return;
        }

        const totalAtRecipeScale = calculateServingTotal(servingQuantity, servingUnit, recipeData);
        if (totalAtRecipeScale === null || totalAtRecipeScale <= 0 || !recipeData.yieldQuantity || !recipeData.yieldUnit) {
            setStatus(control, "error", "Portion scale unavailable");
            return;
        }

        const basePortions = totalAtRecipeScale / servingQuantity;
        const targetInYieldUnit = recipeData.yieldQuantity * desiredPortions / basePortions;
        const convertedTarget = convertUnit(targetInYieldUnit, recipeData.yieldUnit, unitSelect.value);
        quantityInput.value = formatNumber(convertedTarget === null ? targetInYieldUnit : convertedTarget);
        if (convertedTarget === null) {
            unitSelect.value = recipeData.yieldUnit;
        }
        scheduleSave(control);
        calculatePortions(control);
    };

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
        const row = control.closest("tr");
        const servingQuantityInput = row?.querySelector("[data-user-serving-quantity]");
        const servingUnitSelect = row?.querySelector("[data-user-serving-unit]");
        const desiredPortionsInput = row?.querySelector("[data-desired-portions]");
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
                    user_serving_size_quantity: servingQuantityInput?.value || "",
                    user_serving_size_unit: servingUnitSelect?.value || "",
                    desired_portions: desiredPortionsInput?.value || "",
                }),
            });
            const payload = await response.json();
            if (!response.ok || !payload.ok) {
                throw new Error(payload.error || "Unable to save forecast.");
            }
            saveState.set(saveUrl, "saved");
            setStatus(control, "saved", "Saved");
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
        quantityInput.addEventListener("input", () => {
            scheduleSave(control);
            calculatePortions(control);
        });
        unitSelect.addEventListener("change", () => {
            scheduleSave(control);
            calculatePortions(control);
        });
        const row = control.closest("tr");
        row?.querySelector("[data-user-serving-quantity]")?.addEventListener("input", () => {
            scheduleSave(control);
            calculatePortions(control);
        });
        row?.querySelector("[data-user-serving-unit]")?.addEventListener("change", () => {
            scheduleSave(control);
            calculatePortions(control);
        });
        row?.querySelector("[data-desired-portions]")?.addEventListener("input", () => {
            scheduleSave(control);
        });
        row?.querySelector("[data-scale-to-portions]")?.addEventListener("click", () => {
            scaleToDesiredPortions(control);
        });
        calculatePortions(control);
    });

    window.addEventListener("beforeunload", (event) => {
        if (!hasUnsyncedChanges()) {
            return;
        }
        event.preventDefault();
        event.returnValue = "";
    });
});
