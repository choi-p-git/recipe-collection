document.addEventListener("DOMContentLoaded", () => {
    const SEARCH_DEBOUNCE_MS = 500;
    const SEARCH_MIN_LENGTH = 2;

    const searchForm = document.getElementById("menu-slot-search-form");
    const assignmentForm = document.getElementById("menu-slot-assignment-form");
    const searchInput = document.getElementById("q");
    const itemTypeSelect = document.getElementById("item_type");
    const resultsBox = document.getElementById("menu-slot-search-results");
    const selectedSummary = document.getElementById("menu-slot-selected-summary");
    const selectedInputs = document.getElementById("menu-slot-selected-inputs");
    const initialSelectedNode = document.getElementById("menu-slot-initial-selected");
    const initialSearchResultsNode = document.getElementById("menu-slot-initial-search-results");

    if (
        !searchForm ||
        !assignmentForm ||
        !searchInput ||
        !itemTypeSelect ||
        !resultsBox ||
        !selectedSummary ||
        !selectedInputs ||
        !initialSelectedNode ||
        !initialSearchResultsNode
    ) {
        return;
    }

    const selectedItems = new Map();
    const initialSelectedItems = JSON.parse(initialSelectedNode.textContent || "[]");
    const initialSearchResults = JSON.parse(initialSearchResultsNode.textContent || "[]");
    const initialSearchTerm = searchInput.value.trim();
    let debounceTimer = null;
    let requestToken = 0;

    initialSelectedItems.forEach((item) => {
        selectedItems.set(String(item.item_id), item);
    });

    function formatItemType(itemType) {
        return String(itemType)
            .replace("_", " ")
            .replace(/\b\w/g, (character) => character.toUpperCase());
    }

    function syncSelectedInputs() {
        selectedInputs.innerHTML = "";

        Array.from(selectedItems.keys())
            .sort((leftId, rightId) => Number(leftId) - Number(rightId))
            .forEach((itemId) => {
                const hiddenInput = document.createElement("input");
                hiddenInput.type = "hidden";
                hiddenInput.name = "selected_item_ids";
                hiddenInput.value = itemId;
                selectedInputs.appendChild(hiddenInput);
            });
    }

    function renderSelectedSummary() {
        if (!selectedItems.size) {
            selectedSummary.innerHTML = '<p class="muted">No items selected yet.</p>';
            return;
        }

        const orderedItems = Array.from(selectedItems.values()).sort((leftItem, rightItem) =>
            leftItem.item_name.localeCompare(rightItem.item_name),
        );
        const list = document.createElement("ol");
        list.className = "item-detail-list";

        orderedItems.forEach((item) => {
            const listItem = document.createElement("li");
            const strong = document.createElement("strong");
            strong.textContent = item.item_name;

            const meta = document.createElement("span");
            meta.className = "muted";
            meta.textContent = ` (${formatItemType(item.item_type)})`;

            listItem.appendChild(strong);
            listItem.appendChild(meta);
            list.appendChild(listItem);
        });

        selectedSummary.innerHTML = "";
        selectedSummary.appendChild(list);
    }

    function clearResults() {
        resultsBox.innerHTML = "";
    }

    function renderResultsMessage(message) {
        clearResults();
        const messageNode = document.createElement("p");
        messageNode.className = "muted menu-search-message";
        messageNode.textContent = message;
        resultsBox.appendChild(messageNode);
    }

    function buildCardForResult(result) {
        const label = document.createElement("label");
        label.className = "checkbox-card menu-search-result-card";

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = String(result.item_id);
        checkbox.checked = selectedItems.has(String(result.item_id));

        checkbox.addEventListener("change", () => {
            const itemId = String(result.item_id);
            if (checkbox.checked) {
                selectedItems.set(itemId, result);
            } else {
                selectedItems.delete(itemId);
            }
            syncSelectedInputs();
            renderSelectedSummary();
        });

        const content = document.createElement("span");
        const title = document.createElement("strong");
        title.textContent = result.item_name;

        const meta = document.createElement("span");
        meta.className = "muted";
        meta.textContent = `${formatItemType(result.item_type)} | ID ${result.item_id}`;

        content.appendChild(title);
        content.appendChild(document.createElement("br"));
        content.appendChild(meta);

        label.appendChild(checkbox);
        label.appendChild(content);
        return label;
    }

    function renderResults(results, query) {
        clearResults();

        if (!query) {
            renderResultsMessage("Enter a search term to find live recipes and base foods for this slot.");
            return;
        }

        if (query.length < SEARCH_MIN_LENGTH) {
            renderResultsMessage(`Type at least ${SEARCH_MIN_LENGTH} characters to search.`);
            return;
        }

        if (!results.length) {
            renderResultsMessage("No matching live items found.");
            return;
        }

        results.forEach((result) => {
            resultsBox.appendChild(buildCardForResult(result));
        });
    }

    async function runSearch(query) {
        const trimmedQuery = query.trim();

        if (!trimmedQuery) {
            renderResults([], "");
            return;
        }

        if (trimmedQuery.length < SEARCH_MIN_LENGTH) {
            renderResults([], trimmedQuery);
            return;
        }

        const currentToken = requestToken + 1;
        requestToken = currentToken;
        renderResultsMessage("Searching live items...");

        try {
            const params = new URLSearchParams({
                q: trimmedQuery,
                item_type: itemTypeSelect.value,
            });
            const response = await fetch(`/api/items/search?${params.toString()}`);
            const payload = await response.json();

            if (currentToken !== requestToken || trimmedQuery !== searchInput.value.trim()) {
                return;
            }

            renderResults(payload.items || [], trimmedQuery);
        } catch (error) {
            console.error("Menu slot search failed:", error);
            renderResultsMessage("Search failed. Try again.");
        }
    }

    function queueSearch() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            runSearch(searchInput.value);
        }, SEARCH_DEBOUNCE_MS);
    }

    searchForm.addEventListener("submit", (event) => {
        event.preventDefault();
        clearTimeout(debounceTimer);
        runSearch(searchInput.value);
    });

    searchInput.addEventListener("input", () => {
        queueSearch();
    });

    itemTypeSelect.addEventListener("change", () => {
        queueSearch();
    });

    syncSelectedInputs();
    renderSelectedSummary();
    renderResults(initialSearchResults, initialSearchTerm);
});
