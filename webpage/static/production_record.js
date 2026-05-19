document.addEventListener("DOMContentLoaded", () => {
    const SAVE_DEBOUNCE_MS = 500;
    const lineRows = Array.from(document.querySelectorAll("[data-production-record-line]"));
    const summary = document.querySelector("[data-production-record-summary]");

    const isFilled = (value) => value !== null && value !== undefined && String(value).trim() !== "";

    const hasCommittedQuantity = (input) => {
        if (!input || !isFilled(input.value)) {
            return false;
        }
        return !(input.dataset.formulaValue && !isFilled(input.dataset.displayValue));
    };

    const updateSummary = () => {
        if (!summary) {
            return;
        }
        const counts = {
            total: lineRows.length,
            recorded: 0,
            unrecorded: 0,
            accurate: 0,
            review: 0,
            miss: 0,
        };
        lineRows.forEach((row) => {
            const actualQuantity = row.querySelector("[data-actual-quantity]");
            const varianceQuantity = row.querySelector("[data-end-service-variance-quantity]");
            const isRecorded = hasCommittedQuantity(actualQuantity) && hasCommittedQuantity(varianceQuantity);
            if (!isRecorded) {
                counts.unrecorded += 1;
                return;
            }
            counts.recorded += 1;
            const level = row.dataset.forecastAccuracyLevel || "";
            if (Object.prototype.hasOwnProperty.call(counts, level)) {
                counts[level] += 1;
            }
        });

        summary.dataset.totalCount = String(counts.total);
        summary.dataset.recordedCount = String(counts.recorded);
        summary.dataset.unrecordedCount = String(counts.unrecorded);
        summary.dataset.accurateCount = String(counts.accurate);
        summary.dataset.reviewCount = String(counts.review);
        summary.dataset.missCount = String(counts.miss);
        summary.querySelector("[data-summary-recorded]").textContent = String(counts.recorded);
        summary.querySelector("[data-summary-unrecorded]").textContent = String(counts.unrecorded);
        summary.querySelector("[data-summary-accurate]").textContent = String(counts.accurate);
        summary.querySelector("[data-summary-review]").textContent = String(counts.review);
        summary.querySelector("[data-summary-miss]").textContent = String(counts.miss);
    };

    const setStatus = (row, state, message) => {
        const status = row.querySelector("[data-line-status]");
        if (!status) {
            return;
        }
        status.textContent = message;
        status.dataset.state = state;
    };

    const renderCalculatedFields = (row, line) => {
        const impliedDemandNode = row.querySelector("[data-implied-demand]");
        const accuracyNode = row.querySelector("[data-forecast-accuracy]");
        if (!impliedDemandNode || !accuracyNode) {
            return;
        }
        row.dataset.forecastAccuracyLevel = line.forecast_accuracy_level || "";
        if (line.implied_demand_quantity === null || line.implied_demand_quantity === undefined) {
            impliedDemandNode.textContent = "--";
        } else {
            impliedDemandNode.textContent = `${line.implied_demand_quantity_display} ${line.implied_demand_unit_label || line.implied_demand_unit}`;
        }
        if (line.forecast_error_quantity === null || line.forecast_error_quantity === undefined) {
            accuracyNode.textContent = "--";
            return;
        }
        accuracyNode.textContent = `${line.forecast_error_quantity_display} ${line.forecast_error_unit_label || line.forecast_error_unit} (${line.forecast_error_percent_display}%)`;
    };

    const syncReasonNoteVisibility = (row) => {
        const reasonSelect = row.querySelector("[data-reason-code]");
        const reasonNote = row.querySelector("[data-reason-note]");
        if (!reasonSelect || !reasonNote) {
            return;
        }
        reasonNote.classList.toggle("hidden", reasonSelect.value !== "other");
    };

    const applySavedInputValue = (input, submittedValue, savedValue, formulaValue = "") => {
        if (!input || savedValue === undefined) {
            return;
        }
        const currentValue = input.value;
        const isFocused = document.activeElement === input;
        const userContinuedTyping = isFocused && currentValue !== submittedValue;
        const activeFormulaDraft = isFocused && formulaValue;
        if (userContinuedTyping || activeFormulaDraft) {
            return;
        }
        input.value = savedValue;
    };

    const setFormulaMetadata = (input, formulaValue, displayValue) => {
        if (!input) {
            return;
        }
        input.dataset.formulaValue = formulaValue || "";
        input.dataset.displayValue = displayValue || "";
    };

    const syncFormulaFocusBehavior = (input) => {
        if (!input) {
            return;
        }
        input.addEventListener("focus", () => {
            if (!input.dataset.formulaValue) {
                return;
            }
            input.value = input.dataset.formulaValue;
            window.setTimeout(() => input.select(), 0);
        });
        input.addEventListener("blur", () => {
            if (!input.dataset.formulaValue || input.value !== input.dataset.formulaValue) {
                return;
            }
            input.value = input.dataset.displayValue || input.dataset.formulaValue;
        });
    };

    const saveLine = async (row) => {
        const saveUrl = row.dataset.saveUrl;
        if (!saveUrl) {
            return;
        }
        const quantityInput = row.querySelector("[data-actual-quantity]");
        const unitSelect = row.querySelector("[data-actual-unit]");
        const varianceQuantityInput = row.querySelector("[data-end-service-variance-quantity]");
        const varianceUnitSelect = row.querySelector("[data-end-service-variance-unit]");
        const reasonSelect = row.querySelector("[data-reason-code]");
        const reasonNoteInput = row.querySelector("[data-reason-note]");
        const notesInput = row.querySelector("[data-line-notes]");
        const submittedActualQuantity = quantityInput?.value || "";
        const submittedVarianceQuantity = varianceQuantityInput?.value || "";

        setStatus(row, "saving", "Saving...");
        try {
            const response = await fetch(saveUrl, {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    actual_quantity: submittedActualQuantity,
                    actual_unit: unitSelect?.value || "",
                    end_service_variance_quantity: submittedVarianceQuantity,
                    end_service_variance_unit: varianceUnitSelect?.value || "",
                    reason_code: reasonSelect?.value || "",
                    reason_note: reasonNoteInput?.value || "",
                    notes: notesInput?.value || "",
                }),
            });
            const payload = await response.json();
            if (!response.ok || !payload.ok) {
                throw new Error(payload.error || "Unable to save production line.");
            }
            renderCalculatedFields(row, payload.line);
            setFormulaMetadata(
                quantityInput,
                payload.line.actual_quantity_formula,
                payload.line.actual_quantity_display
            );
            setFormulaMetadata(
                varianceQuantityInput,
                payload.line.end_service_variance_quantity_formula,
                payload.line.end_service_variance_quantity_display
            );
            const actualFormula = payload.line.actual_quantity_formula || "";
            const varianceFormula = payload.line.end_service_variance_quantity_formula || "";
            applySavedInputValue(
                quantityInput,
                submittedActualQuantity,
                payload.line.actual_quantity_display || actualFormula,
                actualFormula
            );
            applySavedInputValue(
                varianceQuantityInput,
                submittedVarianceQuantity,
                payload.line.end_service_variance_quantity_display || varianceFormula,
                varianceFormula
            );
            updateSummary();
            setStatus(row, "saved", "Saved");
        } catch (error) {
            setStatus(row, "error", error.message || "Save failed");
        }
    };

    const scheduleSave = (row) => {
        const previousTimer = row.dataset.saveTimer;
        if (previousTimer) {
            window.clearTimeout(Number(previousTimer));
        }
        setStatus(row, "dirty", "Unsaved");
        const timer = window.setTimeout(() => {
            saveLine(row);
        }, SAVE_DEBOUNCE_MS);
        row.dataset.saveTimer = String(timer);
    };

    lineRows.forEach((row) => {
        if (row.dataset.isPosted === "true") {
            syncReasonNoteVisibility(row);
            return;
        }
        row.querySelector("[data-copy-forecast]")?.addEventListener("click", () => {
            const quantityInput = row.querySelector("[data-actual-quantity]");
            const unitSelect = row.querySelector("[data-actual-unit]");
            if (quantityInput) {
                quantityInput.value = row.dataset.forecastQuantity || "";
            }
            if (unitSelect && row.dataset.forecastUnit) {
                unitSelect.value = row.dataset.forecastUnit;
                window.enhanceAdvancedUnitSelects?.();
            }
            scheduleSave(row);
        });
        row.querySelector("[data-zero-variance]")?.addEventListener("click", () => {
            const varianceQuantityInput = row.querySelector("[data-end-service-variance-quantity]");
            const varianceUnitSelect = row.querySelector("[data-end-service-variance-unit]");
            const actualUnitSelect = row.querySelector("[data-actual-unit]");
            if (varianceQuantityInput) {
                varianceQuantityInput.value = "0";
            }
            if (varianceUnitSelect) {
                varianceUnitSelect.value = actualUnitSelect?.value || row.dataset.forecastUnit || varianceUnitSelect.value;
                window.enhanceAdvancedUnitSelects?.();
            }
            scheduleSave(row);
        });
        row.querySelector("[data-actual-quantity]")?.addEventListener("input", () => {
            scheduleSave(row);
        });
        syncFormulaFocusBehavior(row.querySelector("[data-actual-quantity]"));
        row.querySelector("[data-actual-unit]")?.addEventListener("change", () => {
            scheduleSave(row);
        });
        row.querySelector("[data-end-service-variance-quantity]")?.addEventListener("input", () => {
            scheduleSave(row);
        });
        syncFormulaFocusBehavior(row.querySelector("[data-end-service-variance-quantity]"));
        row.querySelector("[data-end-service-variance-unit]")?.addEventListener("change", () => {
            scheduleSave(row);
        });
        row.querySelector("[data-reason-code]")?.addEventListener("change", () => {
            syncReasonNoteVisibility(row);
            scheduleSave(row);
        });
        row.querySelector("[data-reason-note]")?.addEventListener("input", () => {
            scheduleSave(row);
        });
        row.querySelector("[data-line-notes]")?.addEventListener("input", () => {
            scheduleSave(row);
        });
        syncReasonNoteVisibility(row);
    });
    updateSummary();

    window.enhanceAdvancedUnitSelects?.();
});
