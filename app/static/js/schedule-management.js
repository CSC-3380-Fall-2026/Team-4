(() => {
// Manage the selected schedule and its local add, edit, and remove interactions.
const {
    apiRequest,
    loadScheduleData,
    getSelectedSchedule,
    scheduleColors,
    scheduleState,
    clearError,
    showError,
} = window.SchedulePrototype;

const schedulePicker = document.querySelector("#schedule-picker");
const calendarToggle = document.querySelector("#schedule-calendar-toggle");
const scheduleAddButton = document.querySelector("#schedule-add");
const scheduleEditButton = document.querySelector("#schedule-edit");
const scheduleDialog = document.querySelector("#add-schedule-dialog");
const scheduleForm = document.querySelector("#add-schedule-form");
const editScheduleDialog = document.querySelector("#edit-schedule-dialog");
const editScheduleForm = document.querySelector("#edit-schedule-form");

const createColorOption = (color) => {
    // Keep form labels and available choices in sync with the shared color palette
    const option = document.createElement("option");
    option.value = color;
    option.textContent = scheduleColors[color].label;
    return option;
};

const initializeColorSelects = () => {
    // Both add and edit forms use the same schedule color options
    document.querySelectorAll('select[name="color"]').forEach((select) => {
        Object.keys(scheduleColors).forEach((color) => select.append(createColorOption(color)));
    });
};

const renderSchedulePicker = () => {
    // Rebuild options from state so newly added, renamed, and removed schedules appear
    schedulePicker.replaceChildren();
    scheduleState.schedules.forEach((schedule) => {
        const option = document.createElement("option");
        option.value = schedule.id;
        option.dataset.color = schedule.color;
        option.textContent = schedule.name;
        schedulePicker.append(option);
    });
    schedulePicker.value = scheduleState.selectedScheduleId;

    // Remove old schedule colors before applying the newly selected schedule's color
    const pickerClassNames = Object.values(scheduleColors).flatMap(
        ({ picker }) => picker.split(" "),
    );
    schedulePicker.classList.remove(...pickerClassNames);
    const selectedColorClasses = scheduleColors[getSelectedSchedule().color].picker.split(" ");
    schedulePicker.classList.add(...selectedColorClasses);
    document.querySelector(".schedule-picker-chevron").className =
        `schedule-picker-chevron pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 ${selectedColorClasses.at(-1)}`;

    editScheduleForm.querySelector("[data-remove-schedule]").disabled =
        scheduleState.schedules.length <= 1;
};

const initializeScheduleManagement = (renderSchedule) => {
    initializeColorSelects();

    schedulePicker.addEventListener("change", () => {
        // Changing the active schedule refreshes all schedule-dependent page content
        scheduleState.selectedScheduleId = schedulePicker.value;
        renderSchedule();
    });

    // The checkbox only changes calendar visibility; use the shared renderer for consistency
    calendarToggle.addEventListener("change", renderSchedule);

    scheduleAddButton.addEventListener("click", () => {
        // Start a fresh add flow without carrying over old input or validation messages
        scheduleForm.reset();
        clearError(scheduleForm.querySelector("[data-form-error]"));
        scheduleDialog.showModal();
    });

    scheduleForm.addEventListener("submit", async (submitEvent) => {
        submitEvent.preventDefault();
        const errorElement = scheduleForm.querySelector("[data-form-error]");
        clearError(errorElement);
        // Run native constraints first, then validate the trimmed schedule name
        if (!scheduleForm.reportValidity()) {
            return;
        }

        const formData = new FormData(scheduleForm);
        const name = String(formData.get("name"));
        try {
            const schedule = await apiRequest("/api/schedules", {
                method: "POST",
                body: JSON.stringify({ name, color: String(formData.get("color")) }),
            });
            await loadScheduleData();
            scheduleState.selectedScheduleId = schedule.id;
            scheduleDialog.close();
            renderSchedule();
        } catch (error) {
            showError(errorElement, error.message);
        }
    });

    scheduleEditButton.addEventListener("click", () => {
        const selectedSchedule = getSelectedSchedule();
        // Populate the form from the active schedule before opening the edit dialog.
        editScheduleForm.elements.namedItem("name").value = selectedSchedule.name;
        editScheduleForm.elements.namedItem("color").value = selectedSchedule.color;
        clearError(editScheduleForm.querySelector("[data-form-error]"));
        editScheduleDialog.showModal();
    });

    editScheduleForm.addEventListener("submit", async (submitEvent) => {
        submitEvent.preventDefault();
        const errorElement = editScheduleForm.querySelector("[data-form-error]");
        clearError(errorElement);
        if (!editScheduleForm.reportValidity()) {
            return;
        }

        const formData = new FormData(editScheduleForm);
        const name = String(formData.get("name"));
        const selectedSchedule = getSelectedSchedule();
        try {
            await apiRequest(`/api/schedules/${encodeURIComponent(selectedSchedule.id)}`, {
                method: "PUT",
                body: JSON.stringify({ name, color: String(formData.get("color")) }),
            });
            await loadScheduleData();
            editScheduleDialog.close();
            renderSchedule();
        } catch (error) {
            showError(errorElement, error.message);
        }
    });

    editScheduleForm.querySelector("[data-remove-schedule]").addEventListener("click", async () => {
        const selectedSchedule = getSelectedSchedule();
        // Keep at least one schedule available for the page's picker and event forms.
        if (scheduleState.schedules.length <= 1) {
            return;
        }
        if (!window.confirm(`Remove the "${selectedSchedule.name}" schedule and all its events?`)) {
            return;
        }
        clearError(editScheduleForm.querySelector("[data-form-error]"));
        try {
            await apiRequest(`/api/schedules/${encodeURIComponent(selectedSchedule.id)}`, {
                method: "DELETE",
            });
            scheduleState.selectedScheduleId = "";
            await loadScheduleData();
            editScheduleDialog.close();
            renderSchedule();
        } catch (error) {
            showError(editScheduleForm.querySelector("[data-form-error]"), error.message);
        }
    });
};

Object.assign(window.SchedulePrototype, {
    renderSchedulePicker,
    initializeScheduleManagement,
});
})();
