(() => {
    const SAVE_DEBOUNCE_MS = 500;
    const countTypeLabels = {
        counted_by_each_only: "counted by each only",
        counted_by_case_only: "counted by case only",
        counted_by_each_and_case: "counted by each and case",
    };

    const openDialog = (dialog) => {
        if (!dialog) {
            return;
        }
        if (typeof dialog.showModal === "function") {
            dialog.showModal();
        } else {
            dialog.setAttribute("open", "open");
        }
    };

    const closeDialog = (dialog) => {
        if (!dialog) {
            return;
        }
        if (typeof dialog.close === "function") {
            dialog.close();
        } else {
            dialog.removeAttribute("open");
        }
    };

    document.querySelectorAll("[data-dialog-open]").forEach((button) => {
        button.addEventListener("click", () => {
            openDialog(document.getElementById(button.dataset.dialogOpen));
        });
    });

    document.querySelectorAll("[data-dialog-close]").forEach((button) => {
        button.addEventListener("click", () => {
            closeDialog(button.closest("dialog"));
        });
    });

    document.querySelectorAll("[data-confirm-delete]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (!window.confirm(form.dataset.confirmDelete)) {
                event.preventDefault();
            }
        });
    });

    document.querySelectorAll("[data-inline-rename-open]").forEach((button) => {
        button.addEventListener("click", () => {
            const form = document.getElementById(button.dataset.inlineRenameOpen);
            if (!form) {
                return;
            }
            form.hidden = false;
            form.querySelector("input[name='location_name']")?.focus();
        });
    });

    document.querySelectorAll("[data-inline-rename-cancel]").forEach((button) => {
        button.addEventListener("click", () => {
            const form = button.closest("form");
            if (form) {
                form.hidden = true;
            }
        });
    });

    const itemDialog = document.getElementById("inventory-item-dialog");
    const itemForm = document.getElementById("inventory-item-form");
    const interpretation = document.querySelector("[data-inventory-interpretation]");
    const itemSelect = document.querySelector("[data-inventory-item-select]");
    const dialogTitle = document.querySelector("[data-inventory-dialog-title]");
    const submitButton = document.querySelector("[data-inventory-submit]");
    const addOnlyFields = document.querySelectorAll("[data-add-only]");
    const editOnlyFields = document.querySelectorAll("[data-edit-only]");
    const editItemName = document.querySelector("[data-edit-item-name]");
    const editItemNumber = document.querySelector("[data-edit-item-number]");
    const overlayCountEach = document.querySelector("[data-overlay-count-each]");
    const overlayCountCase = document.querySelector("[data-overlay-count-case]");
    const defaultItemFormAction = itemForm?.getAttribute("action") || "";

    const setFieldsetInputsDisabled = (container, isDisabled) => {
        container.querySelectorAll("input, select, textarea").forEach((input) => {
            input.disabled = isDisabled;
        });
    };

    const selectedItemName = () => {
        const selected = itemSelect?.selectedOptions?.[0];
        return selected?.textContent?.trim() || "this item";
    };

    const buildPackPhrase = (prefix, packQty, packSize, itemName) => {
        const numericPackQty = Number(packQty);
        const isSingular = Number.isFinite(numericPackQty) && numericPackQty === 1;
        const verb = isSingular ? "is" : "are";
        const packLabel = isSingular ? "pack" : "packs";
        return `${prefix}, there ${verb} ${packQty} ${packLabel} of ${packSize} ${itemName}.`;
    };

    const updateInterpretation = () => {
        if (!itemForm || !interpretation) {
            return;
        }
        const formData = new FormData(itemForm);
        const itemName = itemForm.dataset.editItemName || selectedItemName();
        const packQty = formData.get("pack_quantity");
        const packSize = formData.get("pack_size_text");
        const uom = formData.get("unit_of_measurement") || "Case";
        const countType = formData.get("count_type") || "counted_by_each_only";
        const countLabel = countTypeLabels[countType] || countType;
        if (packQty && packSize && uom === "Case") {
            interpretation.textContent = `${buildPackPhrase("Per case", packQty, packSize, itemName)} It is to be ${countLabel}.`;
            return;
        }
        if (packQty && packSize) {
            interpretation.textContent = `${buildPackPhrase(`Per ${uom.toLowerCase()}`, packQty, packSize, itemName)} It is to be ${countLabel}.`;
            return;
        }
        interpretation.textContent = `${itemName} is measured as ${uom}. It is to be ${countLabel}.`;
    };

    const resetItemDialogForAdd = () => {
        if (!itemForm) {
            return;
        }
        itemForm.reset();
        if (overlayCountEach) overlayCountEach.value = "0";
        if (overlayCountCase) overlayCountCase.value = "0";
        itemForm.action = defaultItemFormAction;
        itemForm.dataset.editItemName = "";
        itemDialog?.classList.remove("is-editing");
        dialogTitle.textContent = "Add Item";
        submitButton.textContent = "Add Item";
        addOnlyFields.forEach((field) => {
            field.hidden = false;
            setFieldsetInputsDisabled(field, false);
        });
        editOnlyFields.forEach((field) => {
            field.hidden = true;
            setFieldsetInputsDisabled(field, true);
        });
        itemSelect.disabled = false;
        updateInterpretation();
    };

    document.querySelectorAll("[data-dialog-open='inventory-item-dialog']").forEach((button) => {
        button.addEventListener("click", resetItemDialogForAdd);
    });

    document.querySelectorAll("[data-inventory-field]").forEach((field) => {
        field.addEventListener("input", updateInterpretation);
        field.addEventListener("change", updateInterpretation);
    });
    itemSelect?.addEventListener("change", updateInterpretation);

    document.querySelectorAll("[data-inventory-edit]").forEach((button) => {
        button.addEventListener("click", () => {
            if (!itemForm) {
                return;
            }
            itemForm.action = `/inventory/location-items/${button.dataset.rowId}/update`;
            itemForm.dataset.editItemName = button.dataset.itemName || "";
            itemDialog?.classList.add("is-editing");
            dialogTitle.textContent = "Edit Item";
            submitButton.textContent = "Save Item";
            addOnlyFields.forEach((field) => {
                field.hidden = true;
                setFieldsetInputsDisabled(field, true);
            });
            editOnlyFields.forEach((field) => {
                field.hidden = false;
                setFieldsetInputsDisabled(field, false);
            });
            if (editItemName) {
                editItemName.textContent = button.dataset.itemName || "Selected item";
            }
            if (editItemNumber) {
                editItemNumber.textContent = button.dataset.itemId ? `Item #${button.dataset.itemId}` : "";
            }
            itemSelect.value = button.dataset.itemId || itemSelect.value;
            itemSelect.disabled = true;
            if (overlayCountEach) overlayCountEach.value = button.dataset.each || "0";
            if (overlayCountCase) overlayCountCase.value = button.dataset.case || "0";
            itemForm.querySelector("[name='pack_quantity']").value = button.dataset.packQuantity || "";
            itemForm.querySelector("[name='pack_size_text']").value = button.dataset.packSize || "";
            itemForm.querySelector("[name='unit_of_measurement']").value = button.dataset.uom || "Case";
            itemForm.querySelector("[name='count_type']").value = button.dataset.countType || "counted_by_each_only";
            updateInterpretation();
            openDialog(itemDialog);
        });
    });

    const setLineStatus = (row, state, message) => {
        const status = row.querySelector("[data-inventory-line-status]");
        if (!status) {
            return;
        }
        status.dataset.state = state;
        status.textContent = message;
        status.setAttribute("aria-label", message);
    };

    const saveInventoryCountRow = async (row) => {
        const form = row.querySelector(".inventory-row-form");
        const saveUrl = row.dataset.saveUrl;
        if (!form || !saveUrl) {
            return;
        }
        const formData = new FormData(form);
        setLineStatus(row, "saving", "Saving...");
        try {
            const response = await fetch(saveUrl, {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    inventory_location_id: formData.get("inventory_location_id") || "",
                    count_each_quantity: formData.get("count_each_quantity") || "0",
                    count_case_quantity: formData.get("count_case_quantity") || "0",
                    pack_quantity: formData.get("pack_quantity") || "",
                    pack_size_text: formData.get("pack_size_text") || "",
                    unit_of_measurement: formData.get("unit_of_measurement") || "",
                    count_type: formData.get("count_type") || "",
                }),
            });
            const payload = await response.json();
            if (!response.ok || !payload.ok) {
                throw new Error(payload.error || "Unable to save inventory count.");
            }
            const quantityCell = row.querySelector("[data-inventory-quantity]");
            if (quantityCell && payload.line) {
                quantityCell.textContent = `${payload.line.quantity_display} ${payload.line.unit_label}`;
            }
            setLineStatus(row, "saved", "\u2713");
        } catch (error) {
            setLineStatus(row, "error", "\u2715");
            const status = row.querySelector("[data-inventory-line-status]");
            if (status) {
                status.title = error.message || "Save failed";
            }
        }
    };

    const scheduleInventoryCountSave = (row) => {
        const previousTimer = row.dataset.saveTimer;
        if (previousTimer) {
            window.clearTimeout(Number(previousTimer));
        }
        setLineStatus(row, "dirty", "Unsaved");
        const timer = window.setTimeout(() => {
            saveInventoryCountRow(row);
        }, SAVE_DEBOUNCE_MS);
        row.dataset.saveTimer = String(timer);
    };

    document.querySelectorAll("[data-inventory-count-row]").forEach((row) => {
        row.querySelectorAll("[data-inventory-count-input]").forEach((input) => {
            input.addEventListener("input", () => {
                scheduleInventoryCountSave(row);
            });
            input.addEventListener("change", () => {
                scheduleInventoryCountSave(row);
            });
        });
    });

    const priceDialog = document.getElementById("inventory-price-history-dialog");
    const priceCopy = document.querySelector("[data-price-history-copy]");
    document.querySelectorAll("[data-price-history-open]").forEach((button) => {
        button.addEventListener("click", () => {
            if (priceCopy) {
                priceCopy.textContent = `Invoice price history for ${button.dataset.itemName || "this item"} is to be implemented.`;
            }
            openDialog(priceDialog);
        });
    });

    const transferDialog = document.getElementById("inventory-transfer-dialog");
    const transferForm = document.getElementById("inventory-transfer-form");
    const transferCopy = document.querySelector("[data-transfer-copy]");
    document.querySelectorAll("[data-transfer-open]").forEach((button) => {
        button.addEventListener("click", () => {
            if (!transferForm) {
                return;
            }
            transferForm.action = `/inventory/location-items/${button.dataset.rowId}/transfer`;
            if (transferCopy) {
                transferCopy.textContent = `Transfer ${button.dataset.itemName || "this item"} to another sub-location.`;
            }
            openDialog(transferDialog);
        });
    });

    updateInterpretation();
})();
