(() => {
// Connect the schedule page's modules and provide one renderer for shared UI updates.
const {
    initializeCalendar,
    renderCalendarEvents,
    renderCategories,
    renderComparison,
    initializeEventForms,
    renderEventRows,
    initializeScheduleManagement,
    renderSchedulePicker,
    initializeDialogs,
    loadScheduleData,
    showError,
} = window.SchedulePrototype;

const calendar = document.querySelector("#schedule-calendar");
const loadError = document.querySelector("#schedule-page-error");

(async () => {
if (calendar) {
    try {
        await loadScheduleData();
    } catch (error) {
        showError(loadError, error.message);
        return;
    }

    // Keep every schedule surface in sync after a schedule or event changes.
    const renderSchedule = () => {
        renderSchedulePicker();
        renderCategories();
        renderEventRows();
        renderCalendarEvents();
        renderComparison();
    };

    initializeDialogs();
    initializeScheduleManagement(renderSchedule);
    initializeEventForms(renderSchedule);
    renderSchedule();
    initializeCalendar();
}
})();
})();
