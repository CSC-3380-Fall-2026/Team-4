(() => {
const { scheduleState } = window.SchedulePrototype;

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

        const metrics = scheduleState.metrics[selector.value];
        const container = document.querySelector(`#schedule-${side}-metrics`);
        container.querySelector('[data-comparison-metric="total-hours"]').textContent = metrics.totalHours;
        container.querySelector('[data-comparison-metric="days-busy"]').textContent = metrics.daysBusy;

        selector.onchange = () => {
            const selectedMetrics = scheduleState.metrics[selector.value];
            container.querySelector('[data-comparison-metric="total-hours"]').textContent =
                selectedMetrics.totalHours;
            container.querySelector('[data-comparison-metric="days-busy"]').textContent =
                selectedMetrics.daysBusy;
        };
    });
};

window.SchedulePrototype.renderComparison = renderComparison;
})();
