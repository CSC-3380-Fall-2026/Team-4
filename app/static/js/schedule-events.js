(() => {
// Render schedule event rows and handle local event form interactions.
const {
    apiRequest,
    formatTime,
    loadScheduleData,
    getSelectedSchedule,
    scheduleColors,
    scheduleState,
    clearError,
    clearScheduleNotice,
    createElement,
    showScheduleConflict,
    showScheduleSuccess,
    showError,
} = window.SchedulePrototype;

const eventRows = document.querySelector("#schedule-event-rows");
const eventDialog = document.querySelector("#add-event-dialog");
const eventForm = document.querySelector("#add-event-form");
const addEventButton = document.querySelector("#add-event-button");
const courseBrowser = eventForm.querySelector("#course-browser");
const courseBrowserItems = eventForm.querySelector("#course-browser-items");
const courseSearch = eventForm.querySelector("#course-search");
const courseSearchButton = eventForm.querySelector("#course-search-button");
const courseSearchEmpty = eventForm.querySelector("#course-search-empty");
const courseAddIcon = eventForm.querySelector("#course-add-icon");
const eventFields = eventForm.querySelector("#event-fields");
const createEventButton = eventForm.querySelector("#create-event-button");
const editEventDialog = document.querySelector("#edit-event-dialog");
const editEventForm = document.querySelector("#edit-event-form");
const scheduleNotice = document.querySelector("#schedule-notice");
const dayAbbreviations = {
    Monday: "M",
    Tuesday: "Tu",
    Wednesday: "W",
    Thursday: "Th",
    Friday: "F",
    Saturday: "Sa",
    Sunday: "Su",
};
let renderCoursePresets = () => {};

const showEventError = (element, error) => {
    if (error.code === "schedule_conflict" && Array.isArray(error.eventNames)) {
        showScheduleConflict(scheduleNotice, error.eventNames);
        return;
    }
    showError(element, error.message);
};

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

const validateEventForm = (form) => {
    return form.reportValidity();
};

const getEventFormPayload = (formData) => ({
    title: String(formData.get("title")).trim(),
    days: formData.getAll("days"),
    start: String(formData.get("start")),
    end: String(formData.get("end")),
    location: String(formData.get("location") || "").trim(),
    guests: String(formData.get("guests") || ""),
    favorite: formData.has("favorite"),
});

const setEventFormMode = (mode) => {
    const isCourse = mode === "course";
    eventForm.dataset.mode = mode;
    courseBrowser.classList.toggle("hidden", !isCourse);
    eventFields.classList.toggle("hidden", isCourse);
    createEventButton.classList.toggle("hidden", isCourse);
    courseSearch.value = "";
    renderCoursePresets("");
};

const initializeEventForms = (renderSchedule) => {
    let courseSearchSequence = 0;
    renderCoursePresets = async (query) => {
        const requestSequence = ++courseSearchSequence;
        const errorElement = eventForm.querySelector("[data-form-error]");
        clearError(errorElement);
        courseBrowserItems.replaceChildren();
        try {
            const courses = await apiRequest(
                `/api/course-presets?query=${encodeURIComponent(query.trim())}`,
            );
            if (requestSequence !== courseSearchSequence) {
                return;
            }
            courses.forEach((course) => {
            const row = createElement("div", "course-item flex flex-row items-center justify-between gap-15 border-b border-neutrals-100 px-6 py-3 transition-colors hover:bg-yellow-50");
            const info = createElement("div", "course-info flex h-fit min-w-0 flex-col gap-2");
            info.append(createElement("p", "text-md font-semibold text-neutrals-900", course.title));
            const details = createElement("div", "flex flex-row flex-wrap gap-2 text-sm text-neutrals-400");
            details.append(
                createElement("span", "", course.semester),
                createElement("span", "", "|"),
                createElement("span", "", course.professor),
                createElement("span", "", "|"),
                createElement("span", "font-semibold text-purple-600", course.enrollment),
            );
            const meetingDetails = createElement("div", "flex flex-row flex-wrap gap-2 text-sm text-yellow-700");
            meetingDetails.append(
                createElement("span", "", course.days.map((day) => dayAbbreviations[day]).join("")),
                createElement("span", "", "|"),
                createElement("span", "", `${formatTime(course.start)} - ${formatTime(course.end)}`),
            );
            info.append(details, meetingDetails);
            const addButton = createElement("button", "add-course-btn flex h-fit shrink-0 cursor-pointer flex-row items-center justify-center gap-2 rounded-md bg-purple-500 px-3 py-2 font-semibold text-neutrals-0 transition-colors hover:bg-purple-600");
            addButton.type = "button";
            addButton.append(
                courseAddIcon.content.firstElementChild.cloneNode(true),
                document.createTextNode(" Add Course"),
            );
            addButton.addEventListener("click", async () => {
                try {
                    const createdEvent = await apiRequest(`/api/schedules/${encodeURIComponent(scheduleState.selectedScheduleId)}/courses`, {
                        method: "POST",
                        body: JSON.stringify({ courseId: course.courseId }),
                    });
                    await loadScheduleData();
                    eventDialog.close();
                    renderSchedule();
                    showScheduleSuccess(scheduleNotice, createdEvent.title);
                } catch (error) {
                    showEventError(errorElement, error);
                }
            });
            row.append(info, addButton);
            courseBrowserItems.append(row);
            });
            courseSearchEmpty.classList.toggle("hidden", courses.length > 0);
        } catch (error) {
            if (requestSequence !== courseSearchSequence) {
                return;
            }
            showError(errorElement, error.message);
            courseSearchEmpty.classList.remove("hidden");
        }
    };

    courseSearch.addEventListener("input", () => {
        renderCoursePresets(courseSearch.value);
    });
    courseSearchButton.addEventListener("click", () => {
        renderCoursePresets(courseSearch.value);
    });

    const courseModeToggle = eventForm.querySelector('input[name="entry-mode"]');
    courseModeToggle.addEventListener("change", () => {
        setEventFormMode(courseModeToggle.checked ? "course" : "event");
    });

    addEventButton.addEventListener("click", () => {
        clearScheduleNotice(scheduleNotice);
        eventForm.reset();
        setEventFormMode("event");
        clearError(eventForm.querySelector("[data-form-error]"));
        eventDialog.showModal();
    });

    eventForm.addEventListener("submit", async (submitEvent) => {
        submitEvent.preventDefault();
        const errorElement = eventForm.querySelector("[data-form-error]");
        clearError(errorElement);
        const formData = new FormData(eventForm);
        if (!validateEventForm(eventForm)) {
            return;
        }
        try {
            const schedule = getSelectedSchedule();
            const createdEvent = await apiRequest(`/api/schedules/${encodeURIComponent(schedule.id)}/events`, {
                method: "POST",
                body: JSON.stringify(getEventFormPayload(formData)),
            });
            await loadScheduleData();
            eventDialog.close();
            renderSchedule();
            showScheduleSuccess(scheduleNotice, createdEvent.title);
        } catch (error) {
            showEventError(errorElement, error);
        }
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
        clearScheduleNotice(scheduleNotice);
        clearError(editEventForm.querySelector("[data-form-error]"));
        editEventDialog.showModal();
    });

    editEventForm.addEventListener("submit", async (submitEvent) => {
        submitEvent.preventDefault();
        const errorElement = editEventForm.querySelector("[data-form-error]");
        clearError(errorElement);
        const formData = new FormData(editEventForm);
        if (!validateEventForm(editEventForm)) {
            return;
        }
        try {
            const schedule = getSelectedSchedule();
            await apiRequest(`/api/schedules/${encodeURIComponent(schedule.id)}/events/${encodeURIComponent(scheduleState.editingEventId)}`, {
                method: "PUT",
                body: JSON.stringify(getEventFormPayload(formData)),
            });
            await loadScheduleData();
            editEventDialog.close();
            renderSchedule();
        } catch (error) {
            showEventError(errorElement, error);
        }
    });

    editEventForm.querySelector("[data-remove-event]").addEventListener("click", async () => {
        const selectedSchedule = getSelectedSchedule();
        const event = selectedSchedule.events.find((item) => item.id === scheduleState.editingEventId);
        if (!event || !window.confirm(`Remove "${event.title}"?`)) {
            return;
        }
        try {
            await apiRequest(`/api/schedules/${encodeURIComponent(selectedSchedule.id)}/events/${encodeURIComponent(event.id)}`, {
                method: "DELETE",
            });
            await loadScheduleData();
            editEventDialog.close();
            renderSchedule();
        } catch (error) {
            showEventError(editEventForm.querySelector("[data-form-error]"), error);
        }
    });
};

Object.assign(window.SchedulePrototype, {
    renderEventRows,
    initializeEventForms,
});
})();
