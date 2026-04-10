document.addEventListener("DOMContentLoaded", () => {
    const navButtons = document.querySelectorAll(".editor-nav-button");
    const sections = document.querySelectorAll(".editor-section");

    const recipeForm = document.getElementById("recipe-editor-form");
    const submitRecipeButton = document.getElementById("submit-recipe-button");

    const recipeItemName = document.getElementById("recipe_item_name");
    const recipeYieldQuantity = document.getElementById("recipe_yield_quantity");
    const recipeYieldUnit = document.getElementById("recipe_yield_unit");
    const recipePrimaryCookingMethod = document.getElementById("recipe_primary_cooking_method");

    const ingredientList = document.getElementById("ingredient-list");
    const addIngredientButton = document.getElementById("add-ingredient-button");

    const methodStepList = document.getElementById("method-step-list");
    const addMethodStepButton = document.getElementById("add-method-step-button");

    const warningGeneral = document.getElementById("warning-general");
    const warningIngredients = document.getElementById("warning-ingredients");
    const warningMethods = document.getElementById("warning-methods");
    const warningClassification = document.getElementById("warning-classification");
    const warningFinish = document.getElementById("warning-finish");

    const finishCheckGeneral = document.getElementById("finish-check-general");
    const finishCheckIngredients = document.getElementById("finish-check-ingredients");
    const finishCheckMethods = document.getElementById("finish-check-methods");
    const finishCheckClassification = document.getElementById("finish-check-classification");

    function normalizeName(value) {
        return value.trim().replace(/\s+/g, " ");
    }

    function showSection(sectionName) {
        sections.forEach((section) => {
            section.classList.remove("active");
        });

        navButtons.forEach((button) => {
            button.classList.remove("active");
        });

        const targetSection = document.getElementById(`section-${sectionName}`);
        const targetButton = document.querySelector(`.editor-nav-button[data-section="${sectionName}"]`);

        if (targetSection) {
            targetSection.classList.add("active");
        }

        if (targetButton) {
            targetButton.classList.add("active");
        }
    }

    navButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const sectionName = button.dataset.section;
            showSection(sectionName);
        });
    });

    addIngredientButton?.addEventListener("click", () => {
        const scrollY = window.scrollY;

        const row = document.createElement("div");
        row.className = "ingredient-row";
        row.innerHTML = `
            <div class="ingredient-search-block">
                <input type="hidden" class="ingredient-item-id">
                <input type="text" placeholder="Search item by name or ID" class="ingredient-search">
                <div class="ingredient-search-results hidden"></div>
            </div>

            <input type="number" step="0.01" placeholder="Qty" class="ingredient-quantity">

            <select class="ingredient-unit">
                <option value="">-- Unit --</option>
                ${buildUnitOptions()}
            </select>

            <div class="row-actions">
                <button type="button" class="move-up">↑</button>
                <button type="button" class="move-down">↓</button>
                <button type="button" class="delete-row">X</button>
            </div>
        `;

        ingredientList.appendChild(row);
        wireRowButtons(row, ingredientList);
        wireValidationInputs(row);
        wireIngredientSearchRow(row);
        validateEditor();
        window.scrollTo(0, scrollY);
    });

    addMethodStepButton?.addEventListener("click", () => {
        const scrollY = window.scrollY;

        const row = document.createElement("div");
        row.className = "method-step-row";
        row.innerHTML = `
            <textarea rows="4" placeholder="Enter recipe step" class="method-step-text"></textarea>

            <div class="row-actions">
                <button type="button" class="move-up">↑</button>
                <button type="button" class="move-down">↓</button>
                <button type="button" class="delete-row">X</button>
            </div>
        `;

        methodStepList.appendChild(row);
        wireRowButtons(row, methodStepList);
        wireValidationInputs(row);
        validateEditor();
        window.scrollTo(0, scrollY);
    });

    function wireExistingRows() {
        document.querySelectorAll(".ingredient-row").forEach((row) => {
            wireRowButtons(row, ingredientList);
            wireValidationInputs(row);
            wireIngredientSearchRow(row);
        });

        document.querySelectorAll(".method-step-row").forEach((row) => {
            wireRowButtons(row, methodStepList);
            wireValidationInputs(row);
        });
    }

    function wireRowButtons(row, container) {
        const moveUp = row.querySelector(".move-up");
        const moveDown = row.querySelector(".move-down");
        const deleteButton = row.querySelector(".delete-row");

        moveUp?.addEventListener("click", () => {
            const previous = row.previousElementSibling;
            if (previous) {
                container.insertBefore(row, previous);
                validateEditor();
            }
        });

        moveDown?.addEventListener("click", () => {
            const next = row.nextElementSibling;
            if (next) {
                container.insertBefore(next, row);
                validateEditor();
            }
        });

        deleteButton?.addEventListener("click", () => {
            if (container.children.length > 1) {
                row.remove();
                validateEditor();
            }
        });
    }

    function wireValidationInputs(scope = document) {
        scope.querySelectorAll("input, select, textarea").forEach((element) => {
            element.addEventListener("input", validateEditor);
            element.addEventListener("change", validateEditor);
        });
    }

    function wireIngredientSearchRow(row) {
        const searchInput = row.querySelector(".ingredient-search");
        const hiddenIdInput = row.querySelector(".ingredient-item-id");
        const resultsBox = row.querySelector(".ingredient-search-results");

        if (!searchInput || !hiddenIdInput || !resultsBox) return;

        let debounceTimer = null;

        searchInput.addEventListener("input", () => {
            hiddenIdInput.value = "";
            validateEditor();

            const query = searchInput.value.trim();

            clearTimeout(debounceTimer);

            if (!query) {
                resultsBox.innerHTML = "";
                resultsBox.classList.add("hidden");
                return;
            }

            debounceTimer = setTimeout(async () => {
                try {
                    const response = await fetch(`/api/items/search?q=${encodeURIComponent(query)}`);
                    const results = await response.json();

                    renderIngredientSearchResults(resultsBox, results, searchInput, hiddenIdInput);
                } catch (error) {
                    console.error("Ingredient search failed:", error);
                    resultsBox.innerHTML = "";
                    resultsBox.classList.add("hidden");
                }
            }, 100);
        });

        searchInput.addEventListener("blur", () => {
            setTimeout(() => {
                resultsBox.classList.add("hidden");
            }, 150);
        });

        searchInput.addEventListener("focus", () => {
            if (resultsBox.innerHTML.trim()) {
                resultsBox.classList.remove("hidden");
            }
        });
    }

    function renderIngredientSearchResults(resultsBox, results, searchInput, hiddenIdInput) {
        resultsBox.innerHTML = "";

        if (!results.length) {
            resultsBox.classList.add("hidden");
            return;
        }

        results.forEach((item) => {
            const option = document.createElement("button");
            option.type = "button";
            option.className = "ingredient-search-result-item";
            option.textContent = `${item.item_name} [${item.item_type}] (ID: ${item.item_id})`;

            option.addEventListener("click", () => {
                searchInput.value = item.item_name;
                hiddenIdInput.value = item.item_id;
                resultsBox.innerHTML = "";
                resultsBox.classList.add("hidden");
                validateEditor();
            });

            resultsBox.appendChild(option);
        });

        resultsBox.classList.remove("hidden");
    }

    function buildUnitOptions() {
        const unitSelect = document.getElementById("recipe_yield_unit");
        if (!unitSelect) return "";

        const options = [];
        for (const option of unitSelect.options) {
            if (option.value) {
                options.push(`<option value="${option.value}">${option.value}</option>`);
            }
        }
        return options.join("");
    }

    function validateGeneral() {
        const itemName = normalizeName(recipeItemName.value);
        const yieldQuantity = parseFloat(recipeYieldQuantity.value);
        const yieldUnit = recipeYieldUnit.value;

        return (
            itemName.length > 0 &&
            !Number.isNaN(yieldQuantity) &&
            yieldQuantity > 0 &&
            yieldUnit.length > 0
        );
    }

    function validateIngredients() {
        const rows = ingredientList.querySelectorAll(".ingredient-row");
        if (rows.length === 0) {
            return false;
        }

        for (const row of rows) {
            const itemId = row.querySelector(".ingredient-item-id")?.value || "";
            const qtyValue = parseFloat(row.querySelector(".ingredient-quantity")?.value || "");
            const unitValue = row.querySelector(".ingredient-unit")?.value || "";

            const isValidRow =
                itemId.length > 0 &&
                !Number.isNaN(qtyValue) &&
                qtyValue > 0 &&
                unitValue.length > 0;

            if (!isValidRow) {
                return false;
            }
        }

        return true;
    }

    function validateMethods() {
        const cookingMethod = recipePrimaryCookingMethod.value;
        const stepRows = methodStepList.querySelectorAll(".method-step-row");

        if (!cookingMethod) {
            return false;
        }

        if (stepRows.length === 0) {
            return false;
        }

        let hasAtLeastOneValidStep = false;

        for (const row of stepRows) {
            const stepText = (row.querySelector(".method-step-text")?.value || "").trim();

            if (stepText.length > 0) {
                hasAtLeastOneValidStep = true;
            }
        }

        return hasAtLeastOneValidStep;
    }

    function validateClassification() {
        return true;
    }

    function setWarningState(element, isValid, isOptional = false) {
        if (!element) return;

        if (isOptional) {
            element.classList.add("is-hidden");
            return;
        }

        if (isValid) {
            element.classList.add("is-hidden");
        } else {
            element.classList.remove("is-hidden");
        }
    }

    function validateEditor() {
        const generalValid = validateGeneral();
        const ingredientsValid = validateIngredients();
        const methodsValid = validateMethods();
        const classificationValid = validateClassification();

        setWarningState(warningGeneral, generalValid);
        setWarningState(warningIngredients, ingredientsValid);
        setWarningState(warningMethods, methodsValid);
        setWarningState(warningClassification, classificationValid, true);

        const allRequiredValid = generalValid && ingredientsValid && methodsValid;
        setWarningState(warningFinish, allRequiredValid);

        finishCheckGeneral.textContent = `General Information: ${generalValid ? "Valid" : "Incomplete"}`;
        finishCheckIngredients.textContent = `Ingredients: ${ingredientsValid ? "Valid" : "Incomplete"}`;
        finishCheckMethods.textContent = `Methods: ${methodsValid ? "Valid" : "Incomplete"}`;
        finishCheckClassification.textContent = "Classification: Optional";

        submitRecipeButton.disabled = !allRequiredValid;
    }

    function collectRecipePayload() {
    const ingredientRows = Array.from(
        ingredientList.querySelectorAll(".ingredient-row")
    );

    const ingredients = ingredientRows.map((row) => ({
        component_item_id: row.querySelector(".ingredient-item-id")?.value || "",
        component_quantity: row.querySelector(".ingredient-quantity")?.value || "",
        component_unit: row.querySelector(".ingredient-unit")?.value || "",
    }));

    const methodRows = Array.from(
        methodStepList.querySelectorAll(".method-step-row")
    );

    const instructionSteps = methodRows.map((row) =>
        row.querySelector(".method-step-text")?.value || ""
    );

    return {
        item_name: recipeItemName.value,
        yield_quantity: recipeYieldQuantity.value,
        yield_unit: recipeYieldUnit.value,
        serving_size_quantity: document.getElementById("recipe_serving_size_quantity")?.value || "",
        serving_size_unit: document.getElementById("recipe_serving_size_unit")?.value || "",
        serving_count: document.getElementById("recipe_serving_count")?.value || "",
        notes: document.getElementById("recipe_notes")?.value || "",
        primary_cooking_method_code: recipePrimaryCookingMethod.value,
        instruction_steps: instructionSteps,
        ingredients: ingredients,
    };
}

async function submitRecipe() {
    const payload = collectRecipePayload();

    try {
        const response = await fetch("/api/recipes", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
        });

        const result = await response.json();

        if (!response.ok || !result.ok) {
            if (result.suggested_name) {
                recipeItemName.value = result.suggested_name;
                validateEditor();
            }

            alert(result.error || "Recipe submission failed.");
            return;
        }

        alert(`Recipe created successfully. New recipe ID: ${result.recipe_item_id}`);
        window.location.href = "/";
    } catch (error) {
        console.error("Recipe submit failed:", error);
        alert("Unexpected error while submitting recipe.");
    }
}

    submitRecipeButton?.addEventListener("click", async () => {
        if (submitRecipeButton.disabled) {
            return;
        }

        await submitRecipe();
    });

    wireExistingRows();
    wireValidationInputs(recipeForm);
    validateEditor();

});