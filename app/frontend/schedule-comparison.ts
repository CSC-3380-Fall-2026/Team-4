import { requiredElement } from "./dom.js";
import { scheduleState } from "./schedule-data.js";

export const renderComparison = (): void => {
    ["A", "B"].forEach((side) => {
        const selector = requiredElement<HTMLSelectElement>(
            `#schedule-selector-${side}`,
        );

        const container = requiredElement(`#schedule-${side}-metrics`);

        const totalHours = requiredElement(
            '[data-comparison-metric="total-hours"]',
            container,
        );

        const daysBusy = requiredElement(
            '[data-comparison-metric="days-busy"]',
            container,
        );

        const previousValue = selector.value;
        selector.replaceChildren();

        scheduleState.schedules.forEach((schedule) => {
            const option = document.createElement("option");

            option.value = schedule.id;
            option.textContent = schedule.name;
            selector.append(option);
        });

        const firstSchedule = scheduleState.schedules[0];

        const selectedExists = scheduleState.schedules.some(
            (schedule) => schedule.id === scheduleState.selectedScheduleId,
        );

        const fallback = side === "A" && selectedExists
            ? scheduleState.selectedScheduleId
            : firstSchedule?.id ?? "";

        selector.value = scheduleState.schedules.some(
            (schedule) => schedule.id === previousValue,
        )
            ? previousValue
            : fallback;

        selector.disabled = !firstSchedule;

        const renderMetrics = (): void => {
            const metrics = scheduleState.metrics[selector.value];

            totalHours.textContent = metrics
                ? String(metrics.totalHours)
                : "—";

            daysBusy.textContent = metrics?.daysBusy ?? "—";
        };

        renderMetrics();
        selector.onchange = renderMetrics;
    });
};
