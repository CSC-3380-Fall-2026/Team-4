import { requiredElement } from "./dom.js";
import { formatTime, scheduleColors, scheduleState, toMinutes, } from "./schedule-data.js";
import { createElement } from "./schedule-ui.js";
const calendarStartMinutes = 0;
const minutesPerRow = 30;
const rowsPerDay = 48;
export const renderCategories = () => {
    const calendar = requiredElement("#schedule-calendar");
    const categories = requiredElement("#schedule-categories", calendar);
    categories.replaceChildren();
    scheduleState.schedules.forEach((schedule) => {
        const item = createElement("li", "flex items-center justify-center gap-1");
        item.append(createElement("span", `size-2 rounded-full ${scheduleColors[schedule.color].dot}`), document.createTextNode(schedule.name));
        categories.append(item);
    });
};
const createCalendarEvent = (schedule, event) => {
    const color = scheduleColors[schedule.color];
    const isSelected = schedule.id === scheduleState.selectedScheduleId;
    const emphasisClasses = isSelected ? "z-20" : "z-10 opacity-60";
    const eventDuration = toMinutes(event.end) - toMinutes(event.start);
    const isCompact = eventDuration <= minutesPerRow * 2;
    const layoutClasses = isCompact
        ? "m-0.5 flex min-h-0 min-w-0 items-center overflow-hidden rounded-lg border px-1 text-[9px] leading-none"
        : "m-0.5 flex min-h-0 min-w-0 flex-col justify-between gap-1 overflow-hidden rounded-lg border px-2 py-1.5 text-xs leading-tight";
    const card = createElement("article", `calendar-event col-start-1 row-(--event-grid-row) ${emphasisClasses} ${layoutClasses} ${color.event}`);
    card.dataset.eventId = event.id;
    card.dataset.scheduleId = schedule.id;
    card.dataset.start = event.start;
    card.dataset.end = event.end;
    card.title =
        `${event.title}, ${formatTime(event.start)} - ${formatTime(event.end)}${event.favorite ? ", favorite" : ""}`;
    if (isCompact) {
        card.setAttribute("aria-label", card.title);
        card.append(createElement("strong", `block truncate font-bold ${color.title}`, `${event.title} · ${formatTime(event.start)}`));
    }
    else {
        const details = createElement("div", "flex flex-col");
        details.append(createElement("strong", `font-bold ${color.title}`, event.title));
        details.append(createElement("span", "event-time", `${formatTime(event.start)} - ${formatTime(event.end)}`));
        card.append(details);
    }
    if (event.favorite && !isCompact) {
        const star = createElement("span", `event-favorite-star text-lg leading-none ${color.favorite}`, "★");
        star.setAttribute("aria-label", "Favorite event");
        card.append(star);
    }
    const firstRow = Math.floor((toMinutes(event.start) - calendarStartMinutes) / minutesPerRow);
    const lastRow = Math.ceil((toMinutes(event.end) - calendarStartMinutes) / minutesPerRow);
    if (firstRow < 0 || lastRow > rowsPerDay || lastRow <= firstRow) {
        throw new RangeError("Event time must be within the calendar and have a positive duration.");
    }
    card.style.setProperty("--event-grid-row", `${firstRow + 1} / ${lastRow + 1}`);
    return card;
};
export const renderCalendarEvents = () => {
    const calendar = requiredElement("#schedule-calendar");
    const calendarToggle = requiredElement("#schedule-calendar-toggle");
    calendar.querySelectorAll(".calendar-day").forEach((day) => {
        day.replaceChildren();
    });
    scheduleState.schedules.forEach((schedule) => {
        schedule.events.forEach((event) => {
            event.days.forEach((dayName) => {
                const dayColumn = calendar.querySelector(`[data-day-name="${dayName}"]`);
                if (!dayColumn) {
                    return;
                }
                const card = createCalendarEvent(schedule, event);
                if (schedule.id === scheduleState.selectedScheduleId
                    && !calendarToggle.checked) {
                    card.classList.add("hidden");
                }
                dayColumn.append(card);
            });
        });
    });
};
export const initializeCalendar = () => {
    const calendar = requiredElement("#schedule-calendar");
    const scrollContainer = calendar.querySelector(".calendar-scroll");
    const dayGrid = calendar.querySelector(".calendar-day");
    if (!scrollContainer || !dayGrid) {
        return;
    }
    const firstEvent = [
        ...calendar.querySelectorAll(".calendar-event:not(.hidden)"),
    ].sort((left, right) => toMinutes(left.dataset.start ?? "00:00")
        - toMinutes(right.dataset.start ?? "00:00"))[0];
    if (!firstEvent) {
        return;
    }
    scrollContainer.scrollTop = 0;
    const eventOffset = firstEvent.getBoundingClientRect().top
        - scrollContainer.getBoundingClientRect().top;
    const stickyHeader = calendar.querySelector(".calendar-day-heading");
    scrollContainer.scrollTop = Math.max(0, eventOffset - (stickyHeader?.offsetHeight ?? 0) - 64);
};
