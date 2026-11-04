(() => {
const { dayOrder, scheduleState, toMinutes } = window.SchedulePrototype;

// Summarize weekly hours and distinct busy days for one schedule.
const getComparisonMetrics = (schedule) => {
    const daysBusy = [...new Set(schedule.events.flatMap((event) => event.days))];
    const totalMinutes = schedule.events.reduce((total, event) => (
        total + (toMinutes(event.end) - toMinutes(event.start)) * event.days.length
    ), 0);
    return {
        totalHours: Math.ceil(totalMinutes / 60),
        daysBusy: daysBusy.sort((left, right) => dayOrder.indexOf(left) - dayOrder.indexOf(right))
            .map((day) => day.slice(0, 3)).join(", ") || "—",
    };
};

const renderComparison = () => {
    ["A", "B"].forEach((side) => {
        const selector = document.querySelector(`#schedule-selector-${side}`);
        // Retain a valid selection when the schedule list is rebuilt.
        const previousValue = selector.value;
        selector.replaceChildren();
        scheduleState.schedules.forEach((schedule) => {
            const option = document.createElement("option");
            option.value = schedule.id;
            option.textContent = schedule.name;
            selector.append(option);
        });
        selector.value = scheduleState.schedules.some((schedule) => schedule.id === previousValue)
            ? previousValue
            : side === "A" ? scheduleState.selectedScheduleId : scheduleState.schedules[0].id;

        const metrics = getComparisonMetrics(
            scheduleState.schedules.find((schedule) => schedule.id === selector.value),
        );
        const container = document.querySelector(`#schedule-${side}-metrics`);
        container.querySelector('[data-comparison-metric="total-hours"]').textContent = metrics.totalHours;
        container.querySelector('[data-comparison-metric="days-busy"]').textContent = metrics.daysBusy;

        selector.onchange = () => {
            const selectedSchedule = scheduleState.schedules.find(
                (schedule) => schedule.id === selector.value,
            );
            const selectedMetrics = getComparisonMetrics(selectedSchedule);
            container.querySelector('[data-comparison-metric="total-hours"]').textContent =
                selectedMetrics.totalHours;
            container.querySelector('[data-comparison-metric="days-busy"]').textContent =
                selectedMetrics.daysBusy;
        };
    });
};

window.SchedulePrototype.renderComparison = renderComparison;
})();
