(() => {
// Render schedule event rows and handle local event form interactions.
const {
    createId,
    formatTime,
    getSelectedSchedule,
    scheduleColors,
    scheduleState,
    toMinutes,
    clearError,
    createElement,
    showError,
} = window.SchedulePrototype;

const eventRows = document.querySelector("#schedule-event-rows");
const eventDialog = document.querySelector("#add-event-dialog");
const eventForm = document.querySelector("#add-event-form");
const addEventButton = document.querySelector("#add-event-button");
const editEventDialog = document.querySelector("#edit-event-dialog");
const editEventForm = document.querySelector("#edit-event-form");

const createEventRow = (schedule, event) => {
    const color = scheduleColors[schedule.color];
    const row = createElement("tr", "cursor-pointer overflow-hidden transition-colors hover:bg-yellow-50");
    row.dataset.eventRow = "";
    row.dataset.eventId = event.id;

    const titleCell = createElement("td", "border-b border-r border-neutrals-100 px-4 py-3 font-semibold");
    const titleButton = createElement("button", `cursor-pointer text-left font-semibold ${color.title} hover:underline`, event.title);
    titleButton.type = "button";
    titleButton.dataset.editEvent = "";
    titleCell.append(titleButton);

    const daysCell = createElement("td", "border-b border-r border-neutrals-100 px-4 py-3", event.days.map((day) => day.slice(0, 3)).join(", "));
    const timeCell = createElement("td", "whitespace-nowrap border-b border-r border-neutrals-100 px-4 py-3", `${formatTime(event.start)} - ${formatTime(event.end)}`);
    const locationCell = createElement("td", "w-2 break-words whitespace-normal border-b border-r border-neutrals-100 px-4 py-3 text-wrap", event.location || "—");

    const guestsCell = createElement("td", "border-b border-r border-neutrals-100 px-4 py-3");
    const guestList = createElement("div", "flex flex-wrap gap-2");
    if (event.guests.length) {
        event.guests.forEach((guest) => guestList.append(createElement("span", "rounded-md bg-neutrals-800 px-2 py-1 text-xs text-white", guest)));
    } else {
        guestList.append(createElement("span", "text-neutrals-400", "—"));
    }
    guestsCell.append(guestList);

    const favoriteCell = createElement("td", "border-b border-neutrals-100 px-4 py-3 text-center");
    const favorite = document.createElement("input");
    favorite.className = `size-4 cursor-not-allowed ${color.accent}`;
    favorite.type = "checkbox";
    favorite.disabled = true;
    favorite.checked = event.favorite;
    favorite.setAttribute("aria-label", `Favorite ${event.title}`);
    favoriteCell.append(favorite);
    row.append(titleCell, daysCell, timeCell, locationCell, guestsCell, favoriteCell);
    return row;
};

const renderEventRows = () => {
    eventRows.replaceChildren();
    const selectedSchedule = getSelectedSchedule();

    if (selectedSchedule.events.length === 0) {
        const row = createElement("tr");
        const cell = createElement("td", "border-b border-neutrals-100 px-4 py-6 text-center text-neutrals-500", "No events in this schedule yet.");
        cell.colSpan = 6;
        row.append(cell);
        eventRows.append(row);
        return;
    }

    selectedSchedule.events.forEach((event) => eventRows.append(createEventRow(selectedSchedule, event)));
};

const validateEventForm = (form, formData, errorElement) => {
    // Check cross-field rules that native form validation cannot express.
    if (formData.getAll("days").length === 0) {
        showError(errorElement, "Select at least one day.");
        return false;
    }
    if (toMinutes(formData.get("end")) <= toMinutes(formData.get("start"))) {
        showError(errorElement, "End time must be after start time.");
        return false;
    }
    return form.reportValidity();
};

const getEventFormData = (formData) => ({
    title: String(formData.get("title")).trim(),
    days: formData.getAll("days"),
    start: String(formData.get("start")),
    end: String(formData.get("end")),
    location: String(formData.get("location") || "").trim(),
    guests: String(formData.get("guests") || "").split(",").map((guest) => guest.trim()).filter(Boolean),
    favorite: formData.has("favorite"),
});

const initializeEventForms = (renderSchedule) => {
    addEventButton.addEventListener("click", () => {
        eventForm.reset();
        clearError(eventForm.querySelector("[data-form-error]"));
        eventDialog.showModal();
    });

    eventForm.addEventListener("submit", (submitEvent) => {
        submitEvent.preventDefault();
        const errorElement = eventForm.querySelector("[data-form-error]");
        clearError(errorElement);
        const formData = new FormData(eventForm);
        if (!validateEventForm(eventForm, formData, errorElement)) {
            return;
        }
        // Event changes are held in the shared JavaScript sample state, not sent to a backend.
        getSelectedSchedule().events.push({ id: createId("event"), ...getEventFormData(formData) });
        eventDialog.close();
        renderSchedule();
    });

    eventRows.addEventListener("click", (clickEvent) => {
        const row = clickEvent.target.closest("[data-event-row]");
        if (!row) {
            return;
        }
        const event = getSelectedSchedule().events.find((item) => item.id === row.dataset.eventId);
        if (!event) {
            return;
        }
        scheduleState.editingEventId = event.id;
        editEventForm.elements.namedItem("title").value = event.title;
        editEventForm.elements.namedItem("start").value = event.start;
        editEventForm.elements.namedItem("end").value = event.end;
        editEventForm.elements.namedItem("location").value = event.location;
        editEventForm.elements.namedItem("guests").value = event.guests.join(", ");
        editEventForm.elements.namedItem("favorite").checked = event.favorite;
        editEventForm.querySelectorAll('input[name="days"]').forEach((input) => {
            input.checked = event.days.includes(input.value);
        });
        clearError(editEventForm.querySelector("[data-form-error]"));
        editEventDialog.showModal();
    });

    editEventForm.addEventListener("submit", (submitEvent) => {
        submitEvent.preventDefault();
        const errorElement = editEventForm.querySelector("[data-form-error]");
        clearError(errorElement);
        const formData = new FormData(editEventForm);
        if (!validateEventForm(editEventForm, formData, errorElement)) {
            return;
        }
        const selectedSchedule = getSelectedSchedule();
        const eventIndex = selectedSchedule.events.findIndex((event) => event.id === scheduleState.editingEventId);
        if (eventIndex === -1) {
            showError(errorElement, "This event is no longer available.");
            return;
        }
        selectedSchedule.events[eventIndex] = { id: scheduleState.editingEventId, ...getEventFormData(formData) };
        editEventDialog.close();
        renderSchedule();
    });

    editEventForm.querySelector("[data-remove-event]").addEventListener("click", () => {
        const selectedSchedule = getSelectedSchedule();
        const eventIndex = selectedSchedule.events.findIndex((event) => event.id === scheduleState.editingEventId);
        if (eventIndex === -1) {
            return;
        }
        if (!window.confirm(`Remove "${selectedSchedule.events[eventIndex].title}"?`)) {
            return;
        }
        selectedSchedule.events.splice(eventIndex, 1);
        editEventDialog.close();
        renderSchedule();
    });
};

Object.assign(window.SchedulePrototype, {
    renderEventRows,
    initializeEventForms,
});
})();
