import { requiredElement, formInput } from "./dom.js";
import { apiRequest, ApiError, errorMessage, formatTime, loadScheduleData, getSelectedSchedule, scheduleColors, scheduleState, } from "./schedule-data.js";
import { clearError, clearScheduleNotice, createElement, showScheduleConflict, showScheduleSuccess, showError, } from "./schedule-ui.js";
const eventRows = requiredElement("#schedule-event-rows");
const eventDialog = requiredElement("#add-event-dialog");
const eventForm = requiredElement("#add-event-form");
const addEventButton = requiredElement("#add-event-button");
const courseBrowser = requiredElement("#course-browser", eventForm);
const courseBrowserItems = requiredElement("#course-browser-items", eventForm);
const courseSearch = requiredElement("#course-search", eventForm);
const courseSearchButton = requiredElement("#course-search-button", eventForm);
const courseSearchEmpty = requiredElement("#course-search-empty", eventForm);
const courseAddIcon = requiredElement("#course-add-icon", eventForm);
const eventFields = requiredElement("#event-fields", eventForm);
const createEventButton = requiredElement("#create-event-button", eventForm);
const editEventDialog = requiredElement("#edit-event-dialog");
const editEventForm = requiredElement("#edit-event-form");
const scheduleNotice = requiredElement("#schedule-notice");
let renderCoursePresets = async () => { };
let courseSearchSequence = 0;
const showEventError = (element, error) => {
    if (error instanceof ApiError
        && error.code === "schedule_conflict"
        && Array.isArray(error.eventNames)) {
        showScheduleConflict(scheduleNotice, error.eventNames);
        return;
    }
    showError(element, errorMessage(error));
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
        event.guests.forEach((guest) => {
            guestList.append(createElement("span", "rounded-md bg-neutrals-800 px-2 py-1 text-xs text-white", guest));
        });
    }
    else {
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
export const renderEventRows = () => {
    eventRows.replaceChildren();
    const selectedSchedule = getSelectedSchedule();
    addEventButton.disabled = !selectedSchedule;
    if (!selectedSchedule || selectedSchedule.events.length === 0) {
        const row = createElement("tr");
        const emptyText = selectedSchedule
            ? "No events in this schedule yet."
            : "Add a schedule to start adding events.";
        const cell = createElement("td", "border-b border-neutrals-100 px-4 py-6 text-center text-neutrals-500", emptyText);
        cell.colSpan = 6;
        row.append(cell);
        eventRows.append(row);
        return;
    }
    selectedSchedule.events.forEach((event) => {
        eventRows.append(createEventRow(selectedSchedule, event));
    });
};
const validateEventForm = (form) => {
    return form.reportValidity();
};
const getEventFormPayload = (formData) => ({
    title: String(formData.get("title")).trim(),
    days: formData.getAll("days").map(String),
    start: String(formData.get("start")),
    end: String(formData.get("end")),
    location: String(formData.get("location") || "").trim(),
    guests: String(formData.get("guests") || ""),
    favorite: formData.has("favorite"),
});
const setEventFormMode = (mode) => {
    const isCourse = mode === "course";
    courseSearchSequence += 1;
    eventForm.dataset.mode = mode;
    delete eventForm.dataset.courseId;
    courseBrowser.classList.toggle("hidden", !isCourse);
    eventFields.classList.toggle("hidden", isCourse);
    createEventButton.classList.toggle("hidden", isCourse);
    eventFields.querySelectorAll("input, select, textarea").forEach((input) => {
        input.disabled = isCourse;
    });
    courseSearch.value = "";
    if (isCourse) {
        void renderCoursePresets("");
    }
};
export const initializeEventForms = (renderSchedule) => {
    renderCoursePresets = async (query) => {
        const requestSequence = ++courseSearchSequence;
        const errorElement = requiredElement("[data-form-error]", eventForm);
        clearError(errorElement);
        courseBrowserItems.replaceChildren();
        try {
            const courses = await apiRequest(`/api/course-presets?query=${encodeURIComponent(query.trim())}`);
            if (requestSequence !== courseSearchSequence) {
                return;
            }
            courses.forEach((course) => {
                const row = createElement("div", "course-item flex flex-row items-center justify-between gap-15 border-b border-neutrals-100 px-6 py-3 transition-colors hover:bg-yellow-50");
                const info = createElement("div", "course-info flex h-fit min-w-0 flex-col gap-2");
                info.append(createElement("p", "text-md font-semibold text-neutrals-900", course.title));
                const details = createElement("div", "flex flex-row flex-wrap gap-2 text-sm text-neutrals-400");
                details.append(createElement("span", "", course.courseName), createElement("span", "", "|"), createElement("span", "", `${course.credit} credit hours`), createElement("span", "", "|"), createElement("span", "font-semibold text-purple-600", course.category));
                info.append(details);
                const addButton = createElement("button", "add-course-btn flex h-fit shrink-0 cursor-pointer flex-row items-center justify-center gap-2 rounded-md bg-purple-500 px-3 py-2 font-semibold text-neutrals-0 transition-colors hover:bg-purple-600");
                addButton.type = "button";
                addButton.append(courseAddIcon.content.cloneNode(true), document.createTextNode(" Add Course"));
                addButton.addEventListener("click", () => {
                    formInput(eventForm, "entry-mode").checked = false;
                    setEventFormMode("event");
                    eventForm.dataset.courseId = course.courseId;
                    formInput(eventForm, "title").value = course.title;
                });
                row.append(info, addButton);
                courseBrowserItems.append(row);
            });
            courseSearchEmpty.classList.toggle("hidden", courses.length > 0);
        }
        catch (error) {
            if (requestSequence !== courseSearchSequence) {
                return;
            }
            showError(errorElement, errorMessage(error));
            courseSearchEmpty.classList.remove("hidden");
        }
    };
    courseSearch.addEventListener("input", () => {
        void renderCoursePresets(courseSearch.value);
    });
    courseSearchButton.addEventListener("click", () => {
        void renderCoursePresets(courseSearch.value);
    });
    const courseModeToggle = formInput(eventForm, "entry-mode");
    courseModeToggle.addEventListener("change", () => {
        setEventFormMode(courseModeToggle.checked ? "course" : "event");
    });
    addEventButton.addEventListener("click", () => {
        if (!getSelectedSchedule()) {
            return;
        }
        clearScheduleNotice(scheduleNotice);
        eventForm.reset();
        setEventFormMode("event");
        clearError(requiredElement("[data-form-error]", eventForm));
        eventDialog.showModal();
    });
    eventForm.addEventListener("submit", async (submitEvent) => {
        submitEvent.preventDefault();
        if (eventForm.dataset.mode === "course") {
            void renderCoursePresets(courseSearch.value);
            return;
        }
        const errorElement = requiredElement("[data-form-error]", eventForm);
        clearError(errorElement);
        const formData = new FormData(eventForm);
        if (!validateEventForm(eventForm)) {
            return;
        }
        try {
            const schedule = getSelectedSchedule();
            if (!schedule) {
                showError(errorElement, "Choose a schedule before adding an event.");
                return;
            }
            const courseId = eventForm.dataset.courseId;
            const createdEvent = await apiRequest(`/api/schedules/${encodeURIComponent(schedule.id)}/${courseId ? "courses" : "events"}`, {
                method: "POST",
                body: JSON.stringify({
                    ...getEventFormPayload(formData),
                    ...(courseId ? { courseId } : {}),
                }),
            });
            await loadScheduleData();
            eventDialog.close();
            renderSchedule();
            showScheduleSuccess(scheduleNotice, createdEvent.title);
        }
        catch (error) {
            showEventError(errorElement, error);
        }
    });
    eventRows.addEventListener("click", (clickEvent) => {
        const target = clickEvent.target;
        if (!(target instanceof Element)) {
            return;
        }
        const row = target.closest("[data-event-row]");
        if (!row) {
            return;
        }
        const event = getSelectedSchedule()?.events.find((item) => item.id === row.dataset.eventId);
        if (!event) {
            return;
        }
        scheduleState.editingEventId = event.id;
        formInput(editEventForm, "title").value = event.title;
        formInput(editEventForm, "start").value = event.start;
        formInput(editEventForm, "end").value = event.end;
        formInput(editEventForm, "location").value = event.location;
        formInput(editEventForm, "guests").value = event.guests.join(", ");
        formInput(editEventForm, "favorite").checked = event.favorite;
        editEventForm.querySelectorAll('input[name="days"]').forEach((input) => {
            input.checked = event.days.includes(input.value);
        });
        clearScheduleNotice(scheduleNotice);
        clearError(requiredElement("[data-form-error]", editEventForm));
        editEventDialog.showModal();
    });
    editEventForm.addEventListener("submit", async (submitEvent) => {
        submitEvent.preventDefault();
        const errorElement = requiredElement("[data-form-error]", editEventForm);
        clearError(errorElement);
        const formData = new FormData(editEventForm);
        if (!validateEventForm(editEventForm)) {
            return;
        }
        try {
            const schedule = getSelectedSchedule();
            const eventId = scheduleState.editingEventId;
            if (!schedule || !eventId) {
                showError(errorElement, "Choose an event before saving.");
                return;
            }
            await apiRequest(`/api/schedules/${encodeURIComponent(schedule.id)}/events/${encodeURIComponent(eventId)}`, {
                method: "PUT",
                body: JSON.stringify(getEventFormPayload(formData)),
            });
            await loadScheduleData();
            editEventDialog.close();
            renderSchedule();
        }
        catch (error) {
            showEventError(errorElement, error);
        }
    });
    requiredElement("[data-remove-event]", editEventForm).addEventListener("click", async () => {
        const selectedSchedule = getSelectedSchedule();
        if (!selectedSchedule) {
            return;
        }
        const event = selectedSchedule.events.find((item) => item.id === scheduleState.editingEventId);
        if (!event || !window.confirm(`Remove "${event.title}"?`)) {
            return;
        }
        try {
            await apiRequest(`/api/schedules/${encodeURIComponent(selectedSchedule.id)}/events/${encodeURIComponent(event.id)}`, { method: "DELETE" });
            await loadScheduleData();
            editEventDialog.close();
            renderSchedule();
        }
        catch (error) {
            showEventError(requiredElement("[data-form-error]", editEventForm), error);
        }
    });
};
