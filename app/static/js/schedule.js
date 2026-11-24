import { initializeCalendar, renderCalendarEvents, renderCategories, } from "./schedule-calendar.js";
import { renderComparison } from "./schedule-comparison.js";
import { errorMessage, loadScheduleData, } from "./schedule-data.js";
import { initializeEventForms, renderEventRows, } from "./schedule-events.js";
import { initializeScheduleManagement, renderSchedulePicker, } from "./schedule-management.js";
import { initializeDialogs, showError, } from "./schedule-ui.js";
const renderSchedule = () => {
    renderSchedulePicker();
    renderCategories();
    renderEventRows();
    renderCalendarEvents();
    renderComparison();
};
const initializeSchedule = async () => {
    if (!document.querySelector("#schedule-calendar")) {
        return;
    }
    const todayIndex = (new Date().getDay() + 6) % 7;
    document.querySelector(`[data-heading-day="${todayIndex}"]`)?.classList.add("today");
    try {
        await loadScheduleData();
        initializeDialogs();
        initializeScheduleManagement(renderSchedule);
        initializeEventForms(renderSchedule);
        renderSchedule();
        initializeCalendar();
    }
    catch (error) {
        showError(document.querySelector("#schedule-page-error"), errorMessage(error));
    }
};
void initializeSchedule();
