document.addEventListener("DOMContentLoaded", () => {
    const dateRange = document.querySelector("[data-menu-date-range]");
    if (dateRange) {
        const startInput = dateRange.querySelector("[data-menu-start-date]");
        const endInput = dateRange.querySelector("[data-menu-end-date]");
        const summary = document.querySelector("[data-menu-date-summary]");
        const hiddenWeekInput = document.querySelector("#menu_length_weeks");

        const parseDate = (value) => {
            if (!value) {
                return null;
            }
            const date = new Date(`${value}T00:00:00`);
            return Number.isNaN(date.getTime()) ? null : date;
        };

        const updateDateRange = () => {
            if (!startInput || !endInput || !summary) {
                return;
            }

            endInput.min = startInput.value || "";
            endInput.setCustomValidity("");

            const startDate = parseDate(startInput.value);
            const endDate = parseDate(endInput.value);

            if (!startDate || !endDate) {
                summary.textContent = "Select a start and end date to calculate menu weeks.";
                summary.classList.remove("is-error");
                return;
            }

            if (endDate < startDate) {
                summary.textContent = "End date must be on or after the start date.";
                summary.classList.add("is-error");
                endInput.setCustomValidity("End date must be on or after the start date.");
                return;
            }

            const daySpan = Math.floor((endDate - startDate) / 86400000);
            const weekCount = Math.floor(daySpan / 7) + 1;
            if (hiddenWeekInput) {
                hiddenWeekInput.value = String(weekCount);
            }
            summary.textContent = `${weekCount} menu week${weekCount === 1 ? "" : "s"} will be created from this date range.`;
            summary.classList.remove("is-error");
        };

        startInput?.addEventListener("input", updateDateRange);
        endInput?.addEventListener("input", updateDateRange);
        updateDateRange();
    }

    const builder = document.querySelector("[data-concept-builder]");
    if (!builder) {
        return;
    }

    const selectedList = builder.querySelector("[data-concept-selected-list]");
    const hiddenInputs = builder.querySelector("[data-concept-hidden-inputs]");
    const optionButtons = Array.from(builder.querySelectorAll(".concept-order-option"));

    if (!selectedList || !hiddenInputs) {
        return;
    }

    const selectedConcepts = Array.from(selectedList.querySelectorAll("[data-concept-value]")).map((item) => ({
        value: item.dataset.conceptValue,
        label: item.dataset.conceptLabel || item.dataset.conceptValue,
    }));

    const renderSelectedConcepts = () => {
        selectedList.innerHTML = "";
        hiddenInputs.innerHTML = "";

        if (!selectedConcepts.length) {
            const emptyState = document.createElement("li");
            emptyState.className = "concept-order-empty-state";
            emptyState.textContent = "No concepts selected yet.";
            selectedList.appendChild(emptyState);
        } else {
            selectedConcepts.forEach((concept, index) => {
                const item = document.createElement("li");
                item.className = "concept-order-selected-item";

                const label = document.createElement("span");
                label.className = "concept-order-selected-label";
                label.textContent = `${index + 1}. ${concept.label}`;
                item.appendChild(label);

                const actions = document.createElement("div");
                actions.className = "concept-order-selected-actions";

                const upButton = document.createElement("button");
                upButton.type = "button";
                upButton.className = "workflow-button workflow-button-secondary";
                upButton.textContent = "Move Up";
                upButton.disabled = index === 0;
                upButton.addEventListener("click", () => {
                    const [movedConcept] = selectedConcepts.splice(index, 1);
                    selectedConcepts.splice(index - 1, 0, movedConcept);
                    renderSelectedConcepts();
                });
                actions.appendChild(upButton);

                const downButton = document.createElement("button");
                downButton.type = "button";
                downButton.className = "workflow-button workflow-button-secondary";
                downButton.textContent = "Move Down";
                downButton.disabled = index === selectedConcepts.length - 1;
                downButton.addEventListener("click", () => {
                    const [movedConcept] = selectedConcepts.splice(index, 1);
                    selectedConcepts.splice(index + 1, 0, movedConcept);
                    renderSelectedConcepts();
                });
                actions.appendChild(downButton);

                const removeButton = document.createElement("button");
                removeButton.type = "button";
                removeButton.className = "workflow-button workflow-button-danger";
                removeButton.textContent = "Remove";
                removeButton.addEventListener("click", () => {
                    selectedConcepts.splice(index, 1);
                    renderSelectedConcepts();
                });
                actions.appendChild(removeButton);

                item.appendChild(actions);
                selectedList.appendChild(item);

                const hiddenInput = document.createElement("input");
                hiddenInput.type = "hidden";
                hiddenInput.name = "concepts";
                hiddenInput.value = concept.value;
                hiddenInputs.appendChild(hiddenInput);
            });
        }

        const selectedValues = new Set(selectedConcepts.map((concept) => concept.value));
        optionButtons.forEach((button) => {
            const isSelected = selectedValues.has(button.dataset.conceptValue);
            button.disabled = isSelected;
            button.textContent = isSelected
                ? `${button.dataset.conceptLabel} Added`
                : `Add ${button.dataset.conceptLabel}`;
        });
    };

    optionButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const conceptValue = button.dataset.conceptValue;
            const conceptLabel = button.dataset.conceptLabel || conceptValue;
            if (selectedConcepts.some((concept) => concept.value === conceptValue)) {
                return;
            }
            selectedConcepts.push({ value: conceptValue, label: conceptLabel });
            renderSelectedConcepts();
        });
    });

    renderSelectedConcepts();
});
