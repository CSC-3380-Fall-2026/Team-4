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
} = window.SchedulePrototype;

const calendar = document.querySelector("#schedule-calendar");

if (calendar) {
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
