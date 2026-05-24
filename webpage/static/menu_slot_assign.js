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
    const initialSearchPage = JSON.parse(
        initialSearchResultsNode.textContent || '{"items":[],"has_more":false,"next_offset":0,"limit":15}',
    );
    const initialSearchTerm = searchInput.value.trim();
    let debounceTimer = null;
    let requestToken = 0;
    let searchState = {
        query: initialSearchTerm,
        hasMore: Boolean(initialSearchPage.has_more),
        nextOffset: initialSearchPage.next_offset || 0,
        isLoadingMore: false,
    };

    initialSelectedItems.forEach((item) => {
        selectedItems.set(String(item.item_id), item);
    });

    function formatItemType(itemType) {
        return String(itemType)
            .replace("_", " ")
            .replace(/\b\w/g, (character) => character.toUpperCase());
    }

    function buildItemDetailUrl(item) {
        const url = new URL(`/recipe-collection/items/${item.item_id}`, window.location.origin);
        if (item.item_type === "recipe" && item.forecast_updated_at) {
            const scaleQuantity = item.effective_forecast_quantity || item.forecast_quantity || "";
            const scaleUnit = item.effective_forecast_unit || item.forecast_unit || "";
            if (scaleQuantity) url.searchParams.set("scale_quantity", scaleQuantity);
            if (scaleUnit) url.searchParams.set("scale_unit", scaleUnit);
            if (item.user_serving_size_quantity) {
                url.searchParams.set("user_serving_size_quantity", item.user_serving_size_quantity);
            }
            if (item.user_serving_size_unit) {
                url.searchParams.set("user_serving_size_unit", item.user_serving_size_unit);
            }
            if (item.desired_portions) {
                url.searchParams.set("desired_portions", item.desired_portions);
            }
        }
        return `${url.pathname}${url.search}`;
    }

    function getSelectedItemIds() {
        return Array.from(selectedItems.keys());
    }

    function syncSearchResultCheckbox(itemId) {
        const checkbox = resultsBox.querySelector(`input[type="checkbox"][value="${CSS.escape(String(itemId))}"]`);
        if (checkbox) {
            checkbox.checked = selectedItems.has(String(itemId));
        }
    }

    function syncSelectedInputs() {
        selectedInputs.innerHTML = "";

        getSelectedItemIds().forEach((itemId) => {
            const hiddenInput = document.createElement("input");
            hiddenInput.type = "hidden";
            hiddenInput.name = "selected_item_ids";
            hiddenInput.value = itemId;
            selectedInputs.appendChild(hiddenInput);
        });
    }

    function replaceSelectedOrder(orderedItemIds) {
        const reorderedItems = new Map();
        orderedItemIds.forEach((itemId) => {
            const item = selectedItems.get(String(itemId));
            if (item) {
                reorderedItems.set(String(itemId), item);
            }
        });
        selectedItems.clear();
        reorderedItems.forEach((item, itemId) => {
            selectedItems.set(itemId, item);
        });
    }

    function moveSelectedItem(itemId, direction) {
        const orderedItemIds = getSelectedItemIds();
        const currentIndex = orderedItemIds.indexOf(String(itemId));
        const targetIndex = currentIndex + direction;
        if (currentIndex === -1 || targetIndex < 0 || targetIndex >= orderedItemIds.length) {
            return;
        }

        const [movedItemId] = orderedItemIds.splice(currentIndex, 1);
        orderedItemIds.splice(targetIndex, 0, movedItemId);
        replaceSelectedOrder(orderedItemIds);
        syncSelectedInputs();
        renderSelectedSummary();
    }

    function removeSelectedItem(itemId) {
        selectedItems.delete(String(itemId));
        syncSearchResultCheckbox(itemId);
        syncSelectedInputs();
        renderSelectedSummary();
    }

    function moveDraggedItemBefore(draggedItemId, targetItemId) {
        if (!selectedItems.has(String(draggedItemId)) || !selectedItems.has(String(targetItemId))) {
            return;
        }
        if (String(draggedItemId) === String(targetItemId)) {
            return;
        }

        const orderedItemIds = getSelectedItemIds().filter((itemId) => itemId !== String(draggedItemId));
        const targetIndex = orderedItemIds.indexOf(String(targetItemId));
        if (targetIndex === -1) {
            return;
        }
        orderedItemIds.splice(targetIndex, 0, String(draggedItemId));
        replaceSelectedOrder(orderedItemIds);
        syncSelectedInputs();
        renderSelectedSummary();
    }

    function renderSelectedSummary() {
        if (!selectedItems.size) {
            selectedSummary.innerHTML = '<p class="muted">No items selected yet.</p>';
            return;
        }

        const list = document.createElement("ol");
        list.className = "item-detail-list menu-assignment-selected-list";
        list.dataset.reorderableList = "menu-slot-items";

        getSelectedItemIds().forEach((itemId, index) => {
            const item = selectedItems.get(itemId);
            const listItem = document.createElement("li");
            listItem.className = "menu-assignment-selected-item";
            listItem.draggable = true;
            listItem.dataset.selectedItemId = String(item.item_id);

            listItem.addEventListener("dragstart", (event) => {
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", String(item.item_id));
                listItem.classList.add("is-dragging");
            });
            listItem.addEventListener("dragend", () => {
                listItem.classList.remove("is-dragging");
            });
            listItem.addEventListener("dragover", (event) => {
                event.preventDefault();
                event.dataTransfer.dropEffect = "move";
            });
            listItem.addEventListener("drop", (event) => {
                event.preventDefault();
                moveDraggedItemBefore(event.dataTransfer.getData("text/plain"), item.item_id);
            });

            const content = document.createElement("span");
            content.className = "menu-assignment-selected-content";
            const strong = document.createElement("strong");
            const link = document.createElement("a");
            link.className = "text-link";
            link.href = buildItemDetailUrl(item);
            link.textContent = item.item_name;

            const meta = document.createElement("span");
            meta.className = "muted";
            meta.textContent = ` (${formatItemType(item.item_type)})`;

            strong.appendChild(link);
            content.appendChild(strong);
            content.appendChild(meta);

            const controls = document.createElement("span");
            controls.className = "menu-assignment-selected-controls";

            const moveUpButton = document.createElement("button");
            moveUpButton.type = "button";
            moveUpButton.className = "icon-button";
            moveUpButton.textContent = "^";
            moveUpButton.title = `Move ${item.item_name} up`;
            moveUpButton.setAttribute("aria-label", `Move ${item.item_name} up`);
            moveUpButton.disabled = index === 0;
            moveUpButton.addEventListener("click", () => {
                moveSelectedItem(item.item_id, -1);
            });

            const moveDownButton = document.createElement("button");
            moveDownButton.type = "button";
            moveDownButton.className = "icon-button";
            moveDownButton.textContent = "v";
            moveDownButton.title = `Move ${item.item_name} down`;
            moveDownButton.setAttribute("aria-label", `Move ${item.item_name} down`);
            moveDownButton.disabled = index === selectedItems.size - 1;
            moveDownButton.addEventListener("click", () => {
                moveSelectedItem(item.item_id, 1);
            });

            const removeButton = document.createElement("button");
            removeButton.type = "button";
            removeButton.className = "icon-button menu-assignment-remove-button";
            removeButton.textContent = "x";
            removeButton.title = `Remove ${item.item_name} from this cell`;
            removeButton.setAttribute("aria-label", `Remove ${item.item_name} from this cell`);
            removeButton.addEventListener("click", () => {
                removeSelectedItem(item.item_id);
            });

            controls.appendChild(moveUpButton);
            controls.appendChild(moveDownButton);
            controls.appendChild(removeButton);

            listItem.appendChild(content);
            listItem.appendChild(controls);
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
        const link = document.createElement("a");
        link.className = "text-link";
        link.href = buildItemDetailUrl(result);
        link.textContent = result.item_name;
        link.addEventListener("click", (event) => {
            event.stopPropagation();
        });

        const meta = document.createElement("span");
        meta.className = "muted";
        meta.textContent = `${formatItemType(result.item_type)} | ID ${result.item_id}`;

        title.appendChild(link);
        content.appendChild(title);
        content.appendChild(document.createElement("br"));
        content.appendChild(meta);

        label.appendChild(checkbox);
        label.appendChild(content);
        return label;
    }

    function renderSearchMoreControl() {
        removeSearchMoreControl();

        if (!searchState.hasMore) {
            return;
        }

        const moreRow = document.createElement("div");
        moreRow.className = "menu-search-more-row";

        const moreButton = document.createElement("button");
        moreButton.type = "button";
        moreButton.className = "page-action-link secondary menu-search-more-button";
        moreButton.textContent = searchState.isLoadingMore ? "Loading more results..." : "Next Results";
        moreButton.disabled = searchState.isLoadingMore;
        moreButton.addEventListener("click", () => {
            loadMoreResults();
        });

        moreRow.appendChild(moreButton);
        resultsBox.appendChild(moreRow);
    }

    function removeSearchMoreControl() {
        const existingMoreRow = resultsBox.querySelector(".menu-search-more-row");
        if (existingMoreRow) {
            existingMoreRow.remove();
        }
    }

    function renderResults(results, query, appendResults = false) {
        if (!appendResults) {
            clearResults();
        } else {
            removeSearchMoreControl();
        }

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

        renderSearchMoreControl();
    }

    function applySearchPage(payload, query, appendResults = false) {
        searchState = {
            query,
            hasMore: Boolean(payload.has_more),
            nextOffset: payload.next_offset || 0,
            isLoadingMore: false,
        };
        renderResults(payload.items || [], query, appendResults);
    }

    async function runSearch(query, offset = 0, appendResults = false) {
        const trimmedQuery = query.trim();

        if (!trimmedQuery) {
            searchState = { query: "", hasMore: false, nextOffset: 0, isLoadingMore: false };
            renderResults([], "");
            return;
        }

        if (trimmedQuery.length < SEARCH_MIN_LENGTH) {
            searchState = { query: trimmedQuery, hasMore: false, nextOffset: 0, isLoadingMore: false };
            renderResults([], trimmedQuery);
            return;
        }

        const currentToken = requestToken + 1;
        requestToken = currentToken;
        const requestedItemType = itemTypeSelect.value;
        if (appendResults) {
            searchState.isLoadingMore = true;
            renderSearchMoreControl();
        } else {
            renderResultsMessage("Searching live items...");
        }

        try {
            const params = new URLSearchParams({
                q: trimmedQuery,
                item_type: requestedItemType,
                offset: String(offset),
            });
            const response = await fetch(`/recipe-collection/api/items/search?${params.toString()}`);
            const payload = await response.json();

            if (
                currentToken !== requestToken ||
                trimmedQuery !== searchInput.value.trim() ||
                requestedItemType !== itemTypeSelect.value
            ) {
                return;
            }

            applySearchPage(payload, trimmedQuery, appendResults);
        } catch (error) {
            console.error("Menu slot search failed:", error);
            searchState.isLoadingMore = false;
            if (appendResults) {
                removeSearchMoreControl();
                renderSearchMoreControl();
            } else {
                renderResultsMessage("Search failed. Try again.");
            }
        }
    }

    function loadMoreResults() {
        if (!searchState.hasMore || searchState.isLoadingMore) {
            return;
        }

        runSearch(searchState.query, searchState.nextOffset, true);
    }

    function queueSearch() {
        searchState.hasMore = false;
        removeSearchMoreControl();
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
    renderResults(initialSearchPage.items || [], initialSearchTerm);
});
