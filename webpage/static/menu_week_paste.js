document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("[data-week-paste-form]");
    const selectCycleButton = document.querySelector("[data-select-cycle-weeks]");
    const grid = document.querySelector(".menu-week-grid");

    if (!form || !selectCycleButton || !grid) {
        return;
    }

    const sourceWeek = Number(grid.dataset.sourceWeek || "1");
    const checkboxes = Array.from(form.querySelectorAll("input[name='selected_weeks']"));

    selectCycleButton.addEventListener("click", () => {
        for (const checkbox of checkboxes) {
            const weekNumber = Number(checkbox.value);
            checkbox.checked = weekNumber !== sourceWeek && ((weekNumber - sourceWeek) % 4 === 0);
        }
    });
});
