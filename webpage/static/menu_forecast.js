document.addEventListener("DOMContentLoaded", () => {
    const controls = Array.from(document.querySelectorAll("[data-forecast-control]"));
    const batchControls = Array.from(document.querySelectorAll("[data-batch-control]"));
    const saveState = new Map();
    const SAVE_DEBOUNCE_MS = 500;
    const PRODUCTION_SUMMARY_REFRESH_MS = 350;
    let productionSummaryRefreshTimer = null;
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

    const readCaseData = (control) => {
        const caseControl = control.querySelector("[data-case-control]");
        return {
            packQuantity: Number(caseControl?.querySelector("[data-case-pack-quantity]")?.value || 0),
            subunitQuantity: Number(caseControl?.querySelector("[data-case-subunit-quantity]")?.value || 0),
            subunitUnit: caseControl?.querySelector("[data-case-subunit-unit]")?.value || "",
        };
    };

    const selectedOptionLabel = (select) => {
        const option = select?.selectedOptions?.[0];
        return option ? option.textContent.trim() : "";
    };

    const calculateEffectiveForecast = (control) => {
        const quantityInput = control.querySelector("[data-forecast-quantity]");
        const unitSelect = control.querySelector("[data-forecast-unit]");
        const forecastQuantity = Number(quantityInput?.value || 0);
        const forecastUnit = unitSelect?.value || "";
        if (forecastUnit !== "case") {
            return {
                quantity: forecastQuantity,
                unit: forecastUnit,
                unitLabel: selectedOptionLabel(unitSelect) || forecastUnit,
                isCase: false,
            };
        }

        const caseData = readCaseData(control);
        const caseSubunitSelect = control.querySelector("[data-case-subunit-unit]");
        const caseBasisId = control.querySelector("[data-case-basis-id]")?.value || "";
        const effectiveQuantity = Number(control.dataset.effectiveForecastQuantity || 0);
        const effectiveUnit = control.dataset.effectiveForecastUnit || "";
        if (caseBasisId && effectiveUnit) {
            return {
                quantity: effectiveQuantity,
                unit: effectiveUnit,
                unitLabel: effectiveUnit,
                isCase: false,
                isAdvancedCase: true,
            };
        }
        return {
            quantity: forecastQuantity * caseData.packQuantity * caseData.subunitQuantity,
            unit: caseData.subunitUnit,
            unitLabel: selectedOptionLabel(caseSubunitSelect) || caseData.subunitUnit,
            isCase: true,
        };
    };

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

        const effectiveForecast = calculateEffectiveForecast(control);
        const forecastQuantity = effectiveForecast.quantity;
        const forecastUnit = effectiveForecast.unit;
        const servingQuantity = Number(servingQuantityInput.value);
        const servingUnit = servingUnitSelect.value;
        if (effectiveForecast.isCase && !effectiveForecast.isAdvancedCase) {
            result.textContent = "Unavailable";
            return;
        }
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
        if (unitSelect.value === "case") {
            setStatus(control, "error", "Portion scale unavailable for case mode");
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

    const readForecastControlForRow = (row) => row?.querySelector("[data-forecast-control]");

    const readProductionDisplayData = (control) => ({
        massQuantity: Number(control.dataset.productionMassQuantity || 0),
        massUnit: control.dataset.productionMassUnit || "",
        volumeQuantity: Number(control.dataset.productionVolumeQuantity || 0),
        volumeUnit: control.dataset.productionVolumeUnit || "",
    });

    const convertProductionQuantity = (control, quantity, fromUnit, toUnit) => {
        if (!toUnit || fromUnit === toUnit) {
            return Number(quantity);
        }
        const directQuantity = convertUnit(quantity, fromUnit, toUnit);
        if (directQuantity !== null) {
            return directQuantity;
        }
        return bridgeMassVolume(quantity, fromUnit, toUnit, readProductionDisplayData(control));
    };

    const syncProductionDisplayControl = (control) => {
        const unitSelect = control.querySelector("[data-production-display-unit]");
        const totalNode = control.querySelector("[data-production-total]");
        const statusNode = control.querySelector("[data-production-display-status]");
        if (!unitSelect || !totalNode) {
            return;
        }
        const targetUnit = unitSelect.value;
        const targetLabel = selectedOptionLabel(unitSelect) || targetUnit;
        const baseQuantity = Number(control.dataset.productionBaseQuantity || 0);
        const baseUnit = control.dataset.productionBaseUnit || "";
        const convertedTotal = convertProductionQuantity(control, baseQuantity, baseUnit, targetUnit);
        if (convertedTotal === null) {
            if (statusNode) statusNode.textContent = "Cannot convert";
            return;
        }

        totalNode.textContent = `${formatNumber(convertedTotal)} ${targetLabel}`;
        control.querySelectorAll("[data-production-batch-quantity]").forEach((batchNode) => {
            const batchQuantity = Number(batchNode.dataset.productionBaseQuantity || 0);
            const batchUnit = batchNode.dataset.productionBaseUnit || baseUnit;
            const convertedBatch = convertProductionQuantity(control, batchQuantity, batchUnit, targetUnit);
            if (convertedBatch !== null) {
                batchNode.textContent = `${formatNumber(convertedBatch)} ${targetLabel}`;
            }
        });
        if (statusNode) statusNode.textContent = "";
    };

    const wireProductionSummaryControls = (scope = document) => {
        scope.querySelectorAll("[data-production-display-control]").forEach((control) => {
            const unitSelect = control.querySelector("[data-production-display-unit]");
            if (!unitSelect || unitSelect.dataset.productionDisplayWired === "1") {
                return;
            }
            unitSelect.dataset.productionDisplayWired = "1";
            unitSelect.addEventListener("change", () => {
                syncProductionDisplayControl(control);
            });
            syncProductionDisplayControl(control);
        });
    };

    const readForecastQuantityForBatch = (batchControl) => {
        const row = batchControl.closest("tr");
        const forecastControl = readForecastControlForRow(row);
        if (!forecastControl) {
            return { quantity: 0, unit: "", unitLabel: "", isCase: false };
        }
        const effectiveForecast = calculateEffectiveForecast(forecastControl);
        const displayUnitSelect = batchControl.querySelector("[data-batch-display-unit]");
        const displayUnit = displayUnitSelect?.value || effectiveForecast.unit;
        const recipeData = readRecipeData(forecastControl);
        let displayQuantity = effectiveForecast.quantity;
        if (displayUnit && displayUnit !== effectiveForecast.unit) {
            displayQuantity = convertUnit(effectiveForecast.quantity, effectiveForecast.unit, displayUnit);
            if (displayQuantity === null) {
                displayQuantity = bridgeMassVolume(effectiveForecast.quantity, effectiveForecast.unit, displayUnit, recipeData);
            }
        }
        if (displayQuantity === null) {
            displayQuantity = effectiveForecast.quantity;
        }
        return {
            quantity: Number(displayQuantity || 0),
            unit: displayUnit || effectiveForecast.unit,
            unitLabel: selectedOptionLabel(displayUnitSelect) || effectiveForecast.unitLabel || displayUnit || "",
            isCase: effectiveForecast.isCase,
        };
    };

    const renumberBatchRows = (batchControl) => {
        const rows = Array.from(batchControl.querySelectorAll("[data-batch-row]"));
        rows.forEach((row, index) => {
            const label = row.querySelector(".muted");
            if (label) {
                label.textContent = `#${index + 1}`;
            }
        });
    };

    const syncBatchUnitLabels = (batchControl, forecast) => {
        if (!batchControl) {
            return;
        }
        const currentForecast = forecast || readForecastQuantityForBatch(batchControl);
        batchControl.querySelectorAll("[data-batch-unit]").forEach((unitNode) => {
            unitNode.textContent = currentForecast.unitLabel || currentForecast.unit || "";
        });
    };

    const syncBatchQuantitiesFromPercents = (batchControl) => {
        if (!batchControl) {
            return;
        }
        const forecast = readForecastQuantityForBatch(batchControl);
        syncBatchUnitLabels(batchControl, forecast);
        const rows = Array.from(batchControl.querySelectorAll("[data-batch-row]"));
        rows.forEach((row) => {
            const percentInput = row.querySelector("[data-batch-percent]");
            const quantityInput = row.querySelector("[data-batch-quantity]");
            if (!percentInput || !quantityInput || !forecast.quantity) {
                return;
            }
            const percent = Number(percentInput.value || 0);
            if (percent > 0) {
                quantityInput.value = formatNumber(forecast.quantity * percent / 100);
            }
        });
    };

    const syncBatchPercentFromQuantity = (batchControl, batchRow) => {
        const forecast = readForecastQuantityForBatch(batchControl);
        syncBatchUnitLabels(batchControl, forecast);
        const percentInput = batchRow.querySelector("[data-batch-percent]");
        const quantityInput = batchRow.querySelector("[data-batch-quantity]");
        if (!percentInput || !quantityInput || !forecast.quantity) {
            return;
        }
        const quantity = Number(quantityInput.value || 0);
        if (quantity > 0) {
            percentInput.value = formatNumber(quantity / forecast.quantity * 100);
        }
    };

    const setBatchStatus = (batchControl, state, message) => {
        const status = batchControl.querySelector("[data-batch-status]");
        if (!status) {
            return;
        }
        status.textContent = message;
        status.dataset.state = state;
    };

    const readBatchSplits = (batchControl) => {
        const rows = Array.from(batchControl.querySelectorAll("[data-batch-row]"));
        return rows.map((row) => ({
            batch_percent: row.querySelector("[data-batch-percent]")?.value || "",
            batch_quantity: row.querySelector("[data-batch-quantity]")?.value || "",
            planned_time: row.querySelector("[data-batch-time]")?.value || "",
        }));
    };

    const saveBatches = async (batchControl) => {
        const saveUrl = batchControl.dataset.batchSaveUrl;
        if (!saveUrl) {
            return;
        }

        saveState.set(saveUrl, "saving");
        setBatchStatus(batchControl, "saving", "Saving...");

        try {
            const response = await fetch(saveUrl, {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    batch_splits: readBatchSplits(batchControl),
                }),
            });
            const payload = await response.json();
            if (!response.ok || !payload.ok) {
                throw new Error(payload.error || "Unable to save batches.");
            }
            saveState.set(saveUrl, "saved");
            setBatchStatus(batchControl, "saved", "Saved");
            scheduleProductionSummaryRefresh();
        } catch (error) {
            saveState.set(saveUrl, "error");
            setBatchStatus(batchControl, "error", error.message || "Save failed");
        }
    };

    const scheduleBatchSave = (batchControl) => {
        const saveUrl = batchControl.dataset.batchSaveUrl;
        const previousTimer = batchControl.dataset.saveTimer;
        if (previousTimer) {
            window.clearTimeout(Number(previousTimer));
        }
        saveState.set(saveUrl, "dirty");
        setBatchStatus(batchControl, "dirty", "Unsaved");
        const timer = window.setTimeout(() => {
            saveBatches(batchControl);
        }, SAVE_DEBOUNCE_MS);
        batchControl.dataset.saveTimer = String(timer);
    };

    const addBatchRow = (batchControl) => {
        const rowsContainer = batchControl.querySelector("[data-batch-rows]");
        const firstRow = batchControl.querySelector("[data-batch-row]");
        if (!rowsContainer || !firstRow) {
            return;
        }
        const clone = firstRow.cloneNode(true);
        clone.querySelector("[data-batch-percent]").value = "";
        clone.querySelector("[data-batch-quantity]").value = "";
        clone.querySelector("[data-batch-time]").value = "";
        rowsContainer.appendChild(clone);
        wireBatchRow(batchControl, clone);
        renumberBatchRows(batchControl);
        syncBatchUnitLabels(batchControl);
        scheduleBatchSave(batchControl);
    };

    function wireBatchRow(batchControl, row) {
        row.querySelector("[data-batch-percent]")?.addEventListener("input", () => {
            syncBatchQuantitiesFromPercents(batchControl);
            scheduleBatchSave(batchControl);
        });
        row.querySelector("[data-batch-quantity]")?.addEventListener("input", () => {
            syncBatchPercentFromQuantity(batchControl, row);
            scheduleBatchSave(batchControl);
        });
        row.querySelector("[data-batch-time]")?.addEventListener("input", () => {
            scheduleBatchSave(batchControl);
        });
    }

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

    const hasPendingSaves = () => {
        for (const state of saveState.values()) {
            if (state === "dirty" || state === "saving") {
                return true;
            }
        }
        return false;
    };

    const refreshProductionSummary = async () => {
        const section = document.querySelector("[data-production-summary-section]");
        if (!section) {
            return;
        }
        if (hasPendingSaves()) {
            scheduleProductionSummaryRefresh();
            return;
        }

        try {
            const response = await fetch(window.location.href, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
                cache: "no-store",
            });
            if (!response.ok) {
                return;
            }
            const html = await response.text();
            const doc = new DOMParser().parseFromString(html, "text/html");
            const nextSection = doc.querySelector("[data-production-summary-section]");
            if (nextSection) {
                section.replaceWith(nextSection);
                window.enhanceAdvancedUnitSelects?.(nextSection);
                wireProductionSummaryControls(nextSection);
            }
        } catch (error) {
            // The next successful save will try again.
        }
    };

    function scheduleProductionSummaryRefresh() {
        if (productionSummaryRefreshTimer) {
            window.clearTimeout(productionSummaryRefreshTimer);
        }
        productionSummaryRefreshTimer = window.setTimeout(
            refreshProductionSummary,
            PRODUCTION_SUMMARY_REFRESH_MS
        );
    }

    const saveForecast = async (control) => {
        const quantityInput = control.querySelector("[data-forecast-quantity]");
        const unitSelect = control.querySelector("[data-forecast-unit]");
        const row = control.closest("tr");
        const servingQuantityInput = row?.querySelector("[data-user-serving-quantity]");
        const servingUnitSelect = row?.querySelector("[data-user-serving-unit]");
        const desiredPortionsInput = row?.querySelector("[data-desired-portions]");
        const casePackQuantityInput = control.querySelector("[data-case-pack-quantity]");
        const caseSubunitQuantityInput = control.querySelector("[data-case-subunit-quantity]");
        const caseSubunitUnitSelect = control.querySelector("[data-case-subunit-unit]");
        const caseBasisIdInput = control.querySelector("[data-case-basis-id]");
        const caseBasisNameInput = control.querySelector("[data-case-basis-name]");
        const caseBasisViewInput = control.querySelector("[data-case-basis-view]");
        const caseBasisRowKeyInput = control.querySelector("[data-case-basis-row-key]");
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
                    case_pack_quantity: casePackQuantityInput?.value || "",
                    case_subunit_quantity: caseSubunitQuantityInput?.value || "",
                    case_subunit_unit: caseSubunitUnitSelect?.value || "",
                    case_basis_component_item_id: caseBasisIdInput?.value || "",
                    case_basis_component_name: caseBasisNameInput?.value || "",
                    case_basis_view_mode: caseBasisViewInput?.value || "",
                    case_basis_row_key: caseBasisRowKeyInput?.value || "",
                }),
            });
            const payload = await response.json();
            if (!response.ok || !payload.ok) {
                throw new Error(payload.error || "Unable to save forecast.");
            }
            if (payload.forecast) {
                control.dataset.effectiveForecastQuantity = String(payload.forecast.calculated_forecast_quantity ?? "");
                control.dataset.effectiveForecastUnit = payload.forecast.calculated_forecast_unit || "";
                calculatePortions(control);
            }
            saveState.set(saveUrl, "saved");
            setStatus(control, "saved", "Saved");
            scheduleProductionSummaryRefresh();
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

    const saveForecastNow = (control) => {
        const previousTimer = control.dataset.saveTimer;
        if (previousTimer) {
            window.clearTimeout(Number(previousTimer));
            control.dataset.saveTimer = "";
        }
        saveForecast(control);
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
            const batchControl = control.closest("tr")?.querySelector("[data-batch-control]");
            if (batchControl) {
                syncBatchQuantitiesFromPercents(batchControl);
            }
        });
        const caseControl = control.querySelector("[data-case-control]");
        const caseOverlay = control.querySelector("[data-case-overlay]");
        const caseIngredientTitle = control.querySelector("[data-case-ingredient-title]");
        const casePackOptionsNode = control.querySelector("[data-case-pack-options]");
        const savedCasePacksByItemId = JSON.parse(casePackOptionsNode?.textContent || "{}");
        const normalizePackValue = (value) => {
            const numberValue = Number(value || 0);
            return Number.isFinite(numberValue) ? numberValue : 0;
        };
        const normalizePackUnit = (value) => String(value || "").trim().toLowerCase();
        const readOverlayCasePack = () => ({
            packQuantity: normalizePackValue(caseOverlay?.querySelector("[data-case-overlay-pack]")?.value),
            subunitQuantity: normalizePackValue(caseOverlay?.querySelector("[data-case-overlay-size]")?.value),
            subunitUnit: normalizePackUnit(caseOverlay?.querySelector("[data-case-overlay-unit]")?.value),
        });
        const readSelectedCaseBasisId = () => {
            const selectedCandidate = caseOverlay?.querySelector("[data-case-candidate]:checked");
            return selectedCandidate?.value || control.querySelector("[data-case-basis-id]")?.value || "";
        };
        const getSavedCasePacksForSelectedBasis = () => {
            const basisId = readSelectedCaseBasisId();
            return basisId ? savedCasePacksByItemId[String(basisId)] || [] : [];
        };
        const casePacksMatch = (casePack, manualPack) => (
            Math.abs(Number(casePack.pack_quantity) - manualPack.packQuantity) < 0.000001 &&
            Math.abs(Number(casePack.subunit_quantity) - manualPack.subunitQuantity) < 0.000001 &&
            normalizePackUnit(casePack.subunit_unit) === manualPack.subunitUnit
        );
        const renderSavedCasePackOptions = () => {
            const select = caseOverlay?.querySelector("[data-case-pack-select]");
            if (!select) {
                return;
            }
            select.innerHTML = "";
            const manualOption = document.createElement("option");
            manualOption.value = "";
            manualOption.textContent = "Manual case size";
            select.appendChild(manualOption);
            getSavedCasePacksForSelectedBasis().forEach((casePack) => {
                const option = document.createElement("option");
                option.value = String(casePack.item_case_pack_id);
                option.textContent = `${casePack.pack_quantity_display} x ${casePack.subunit_quantity_display} ${casePack.subunit_unit}`;
                option.dataset.packQuantity = String(casePack.pack_quantity);
                option.dataset.subunitQuantity = String(casePack.subunit_quantity);
                option.dataset.subunitUnit = casePack.subunit_unit;
                select.appendChild(option);
            });
        };
        const setCasePackStatus = (message) => {
            const status = caseOverlay?.querySelector("[data-case-pack-status]");
            if (status) {
                status.textContent = message;
            }
        };
        const syncCasePackSaveState = () => {
            const saveButton = caseOverlay?.querySelector("[data-save-case-pack]");
            if (!saveButton) {
                return;
            }
            const selectedBasisId = readSelectedCaseBasisId();
            const manualPack = readOverlayCasePack();
            const hasValidPack = Boolean(
                selectedBasisId &&
                manualPack.packQuantity > 0 &&
                manualPack.subunitQuantity > 0 &&
                manualPack.subunitUnit
            );
            const isDuplicate = hasValidPack && getSavedCasePacksForSelectedBasis().some((casePack) =>
                casePacksMatch(casePack, manualPack)
            );
            saveButton.disabled = !hasValidPack || isDuplicate;
            if (!hasValidPack) {
                setCasePackStatus("");
            } else if (isDuplicate) {
                setCasePackStatus("Already saved");
            } else {
                setCasePackStatus("");
            }
        };
        const addSavedCasePackOption = (casePack) => {
            const itemId = String(casePack.item_id);
            if (!savedCasePacksByItemId[itemId]) {
                savedCasePacksByItemId[itemId] = [];
            }
            savedCasePacksByItemId[itemId].unshift(casePack);
            renderSavedCasePackOptions();
            syncCasePackSaveState();
        };
        const setCaseView = (viewMode) => {
            const mode = viewMode || "hierarchical";
            control.querySelectorAll("[data-case-candidates]").forEach((candidateList) => {
                candidateList.classList.toggle("hidden", candidateList.dataset.caseCandidates !== mode);
            });
            control.querySelectorAll("[data-case-view-button]").forEach((button) => {
                const isSelected = button.dataset.caseViewButton === mode;
                button.setAttribute("aria-pressed", String(isSelected));
                button.classList.toggle("button-secondary", !isSelected);
            });
        };
        const closeCaseOverlay = () => {
            caseOverlay?.classList.add("hidden");
            document.body.classList.remove("has-menu-forecast-case-overlay");
        };
        const openCaseOverlay = () => {
            const viewInput = control.querySelector("[data-case-basis-view]");
            const packInput = caseControl?.querySelector("[data-case-pack-quantity]");
            const sizeInput = caseControl?.querySelector("[data-case-subunit-quantity]");
            const unitSelect = caseControl?.querySelector("[data-case-subunit-unit]");
            caseOverlay?.querySelector("[data-case-overlay-pack]")?.setAttribute("value", packInput?.value || "");
            caseOverlay?.querySelector("[data-case-overlay-size]")?.setAttribute("value", sizeInput?.value || "");
            const overlayPack = caseOverlay?.querySelector("[data-case-overlay-pack]");
            const overlaySize = caseOverlay?.querySelector("[data-case-overlay-size]");
            const overlayUnit = caseOverlay?.querySelector("[data-case-overlay-unit]");
            if (overlayPack) overlayPack.value = packInput?.value || "";
            if (overlaySize) overlaySize.value = sizeInput?.value || "";
            if (overlayUnit) overlayUnit.value = unitSelect?.value || "";
            setCaseView(viewInput?.value || "hierarchical");
            renderSavedCasePackOptions();
            syncCasePackSaveState();
            caseOverlay?.classList.remove("hidden");
            document.body.classList.add("has-menu-forecast-case-overlay");
        };
        const applyCaseOverlay = () => {
            const selectedCandidate = caseOverlay?.querySelector("[data-case-candidate]:checked");
            if (!selectedCandidate) {
                setStatus(control, "error", "Select a case ingredient");
                return;
            }
            const overlayPack = caseOverlay.querySelector("[data-case-overlay-pack]");
            const overlaySize = caseOverlay.querySelector("[data-case-overlay-size]");
            const overlayUnit = caseOverlay.querySelector("[data-case-overlay-unit]");
            const packInput = caseControl?.querySelector("[data-case-pack-quantity]");
            const sizeInput = caseControl?.querySelector("[data-case-subunit-quantity]");
            const unitSelect = caseControl?.querySelector("[data-case-subunit-unit]");
            if (packInput) packInput.value = overlayPack?.value || "";
            if (sizeInput) sizeInput.value = overlaySize?.value || "";
            if (unitSelect) unitSelect.value = overlayUnit?.value || "";
            const basisIdInput = control.querySelector("[data-case-basis-id]");
            const basisNameInput = control.querySelector("[data-case-basis-name]");
            const basisViewInput = control.querySelector("[data-case-basis-view]");
            const basisRowKeyInput = control.querySelector("[data-case-basis-row-key]");
            const casePackIdInput = control.querySelector("[data-case-pack-id]");
            const candidateName = selectedCandidate.dataset.caseCandidateName || "";
            if (basisIdInput) basisIdInput.value = selectedCandidate.value;
            if (basisNameInput) basisNameInput.value = candidateName;
            if (basisViewInput) basisViewInput.value = selectedCandidate.dataset.caseCandidateView || "hierarchical";
            if (basisRowKeyInput) basisRowKeyInput.value = selectedCandidate.dataset.caseCandidateRowKey || "";
            if (casePackIdInput) casePackIdInput.value = caseOverlay.querySelector("[data-case-pack-select]")?.value || "";
            if (caseIngredientTitle) {
                caseIngredientTitle.textContent = candidateName ? `Linked to ${candidateName}` : "";
                caseIngredientTitle.classList.toggle("hidden", !candidateName);
            }
            control.dataset.effectiveForecastQuantity = "";
            control.dataset.effectiveForecastUnit = "";
            closeCaseOverlay();
            updateUnitMode();
            saveForecastNow(control);
            syncBatchQuantitiesFromPercents(control.closest("tr")?.querySelector("[data-batch-control]"));
        };
        const saveReusableCasePack = async () => {
            const saveButton = caseOverlay?.querySelector("[data-save-case-pack]");
            const saveUrl = control.dataset.casePackSaveUrl;
            const selectedBasisId = readSelectedCaseBasisId();
            const manualPack = readOverlayCasePack();
            if (!saveUrl || !selectedBasisId || saveButton?.disabled) {
                return;
            }
            saveButton.disabled = true;
            setCasePackStatus("Saving...");
            try {
                const response = await fetch(saveUrl, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        item_id: selectedBasisId,
                        pack_quantity: manualPack.packQuantity,
                        subunit_quantity: manualPack.subunitQuantity,
                        subunit_unit: manualPack.subunitUnit,
                    }),
                });
                const payload = await response.json();
                if (!response.ok || !payload.ok) {
                    throw new Error(payload.error || "Unable to save case size.");
                }
                addSavedCasePackOption(payload.case_pack);
                setCasePackStatus("Saved");
            } catch (error) {
                setCasePackStatus(error.message || "Save failed");
                syncCasePackSaveState();
            }
        };
        const updateUnitMode = () => {
            const isCaseMode = unitSelect.value === "case";
            const isAdvancedCaseMode = isCaseMode && Boolean(control.querySelector("[data-case-basis-id]")?.value);
            const advancedPicker = control.querySelector(".advanced-unit-picker");
            const isAdvancedPanMode = Boolean(advancedPicker && !advancedPicker.classList.contains("hidden"));
            control.classList.toggle("is-case-mode", isCaseMode);
            control.classList.toggle("is-advanced-pan-mode", isAdvancedPanMode && !isCaseMode);
            caseControl?.classList.toggle("hidden", !isCaseMode);
            if (isCaseMode) {
                advancedPicker?.classList.add("hidden");
            } else {
                closeCaseOverlay();
            }
            const row = control.closest("tr");
            row?.querySelector("[data-user-serving-quantity]")?.toggleAttribute("disabled", isCaseMode && !isAdvancedCaseMode);
            row?.querySelector("[data-user-serving-unit]")?.toggleAttribute("disabled", isCaseMode && !isAdvancedCaseMode);
            row?.querySelector("[data-desired-portions]")?.toggleAttribute("disabled", isCaseMode && !isAdvancedCaseMode);
            row?.querySelector("[data-scale-to-portions]")?.toggleAttribute("disabled", isCaseMode && !isAdvancedCaseMode);
        };
        unitSelect.addEventListener("change", () => {
            window.requestAnimationFrame(updateUnitMode);
            scheduleSave(control);
            calculatePortions(control);
            const batchControl = control.closest("tr")?.querySelector("[data-batch-control]");
            if (batchControl) {
                syncBatchQuantitiesFromPercents(batchControl);
            }
        });
        caseControl?.querySelector("[data-case-pack-quantity]")?.addEventListener("input", () => {
            scheduleSave(control);
            syncBatchQuantitiesFromPercents(control.closest("tr")?.querySelector("[data-batch-control]"));
        });
        caseControl?.querySelector("[data-case-subunit-quantity]")?.addEventListener("input", () => {
            scheduleSave(control);
            syncBatchQuantitiesFromPercents(control.closest("tr")?.querySelector("[data-batch-control]"));
        });
        caseControl?.querySelector("[data-case-subunit-unit]")?.addEventListener("change", () => {
            scheduleSave(control);
            syncBatchQuantitiesFromPercents(control.closest("tr")?.querySelector("[data-batch-control]"));
        });
        caseControl?.querySelector("[data-case-config]")?.addEventListener("click", openCaseOverlay);
        caseOverlay?.querySelectorAll("[data-case-view-button]").forEach((button) => {
            button.addEventListener("click", () => {
                setCaseView(button.dataset.caseViewButton);
                renderSavedCasePackOptions();
                syncCasePackSaveState();
            });
        });
        caseOverlay?.querySelectorAll("[data-case-candidate]").forEach((candidate) => {
            candidate.addEventListener("change", () => {
                renderSavedCasePackOptions();
                syncCasePackSaveState();
            });
        });
        caseOverlay?.querySelector("[data-case-pack-select]")?.addEventListener("change", (event) => {
            const option = event.target.selectedOptions[0];
            if (!option || !option.value) {
                syncCasePackSaveState();
                return;
            }
            const overlayPack = caseOverlay.querySelector("[data-case-overlay-pack]");
            const overlaySize = caseOverlay.querySelector("[data-case-overlay-size]");
            const overlayUnit = caseOverlay.querySelector("[data-case-overlay-unit]");
            if (overlayPack) overlayPack.value = option.dataset.packQuantity || "";
            if (overlaySize) overlaySize.value = option.dataset.subunitQuantity || "";
            if (overlayUnit) overlayUnit.value = option.dataset.subunitUnit || "";
            syncCasePackSaveState();
        });
        const markManualCasePack = () => {
            const select = caseOverlay?.querySelector("[data-case-pack-select]");
            if (select) {
                select.value = "";
            }
            syncCasePackSaveState();
        };
        caseOverlay?.querySelector("[data-case-overlay-pack]")?.addEventListener("input", markManualCasePack);
        caseOverlay?.querySelector("[data-case-overlay-size]")?.addEventListener("input", markManualCasePack);
        caseOverlay?.querySelector("[data-case-overlay-unit]")?.addEventListener("change", markManualCasePack);
        caseOverlay?.querySelector("[data-save-case-pack]")?.addEventListener("click", saveReusableCasePack);
        caseOverlay?.querySelectorAll("[data-case-cancel]").forEach((button) => {
            button.addEventListener("click", closeCaseOverlay);
        });
        caseOverlay?.querySelector("[data-case-confirm]")?.addEventListener("click", applyCaseOverlay);
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
        updateUnitMode();
    });

    batchControls.forEach((batchControl) => {
        Array.from(batchControl.querySelectorAll("[data-batch-row]")).forEach((row) => {
            wireBatchRow(batchControl, row);
        });
        batchControl.querySelector("[data-add-batch]")?.addEventListener("click", () => {
            addBatchRow(batchControl);
        });
        batchControl.querySelector("[data-remove-batch]")?.addEventListener("click", () => {
            const rows = Array.from(batchControl.querySelectorAll("[data-batch-row]"));
            if (rows.length <= 1) {
                return;
            }
            rows[rows.length - 1].remove();
            renumberBatchRows(batchControl);
            syncBatchQuantitiesFromPercents(batchControl);
            scheduleBatchSave(batchControl);
        });
        batchControl.querySelector("[data-batch-display-unit]")?.addEventListener("change", () => {
            syncBatchQuantitiesFromPercents(batchControl);
        });
        syncBatchQuantitiesFromPercents(batchControl);
    });

    window.enhanceAdvancedUnitSelects?.(document.querySelector("[data-production-summary-section]") || document);
    wireProductionSummaryControls();

    window.addEventListener("beforeunload", (event) => {
        if (!hasUnsyncedChanges()) {
            return;
        }
        event.preventDefault();
        event.returnValue = "";
    });
});
