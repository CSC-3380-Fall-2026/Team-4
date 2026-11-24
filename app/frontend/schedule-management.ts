import { requiredElement, formInput } from "./dom.js";
import {
    apiRequest,
    errorMessage,
    loadScheduleData,
    getSelectedSchedule,
    scheduleColors,
    scheduleState,
} from "./schedule-data.js";
import { clearError, showError } from "./schedule-ui.js";
import type { ColorName, Schedule, RenderPage } from "./types.js";

const schedulePicker = requiredElement<HTMLSelectElement>(
    "#schedule-picker",
);
const calendarToggle = requiredElement<HTMLInputElement>(
    "#schedule-calendar-toggle",
);
const scheduleAddButton = requiredElement<HTMLButtonElement>(
    "#schedule-add",
);
const scheduleEditButton = requiredElement<HTMLButtonElement>(
    "#schedule-edit",
);
const scheduleDialog = requiredElement<HTMLDialogElement>(
    "#add-schedule-dialog",
);
const scheduleForm = requiredElement<HTMLFormElement>(
    "#add-schedule-form",
);
const editScheduleDialog = requiredElement<HTMLDialogElement>(
    "#edit-schedule-dialog",
);
const editScheduleForm = requiredElement<HTMLFormElement>(
    "#edit-schedule-form",
);

const createColorOption = (color: ColorName): HTMLOptionElement => {
    const option = document.createElement("option");

    option.value = color;
    option.textContent = scheduleColors[color].label;

    return option;
};

const initializeColorSelects = (): void => {
    document.querySelectorAll<HTMLSelectElement>(
        'select[name="color"]',
    ).forEach((select) => {
        (Object.keys(scheduleColors) as ColorName[]).forEach((color) => {
            select.append(createColorOption(color));
        });
    });
};

export const renderSchedulePicker = (): void => {
    schedulePicker.replaceChildren();

    scheduleState.schedules.forEach((schedule) => {
        const option = document.createElement("option");

        option.value = schedule.id;
        option.dataset.color = schedule.color;
        option.textContent = schedule.name;

        schedulePicker.append(option);
    });

    schedulePicker.value = scheduleState.selectedScheduleId;

    const pickerClassNames = Object.values(scheduleColors).flatMap(
        ({ picker }) => picker.split(" "),
    );

    schedulePicker.classList.remove(...pickerClassNames);

    const selectedSchedule = getSelectedSchedule();
    scheduleEditButton.disabled = !selectedSchedule;

    if (!selectedSchedule) {
        return;
    }

    const selectedColorClasses =
        scheduleColors[selectedSchedule.color].picker.split(" ");

    schedulePicker.classList.add(...selectedColorClasses);

    requiredElement(".schedule-picker-chevron").setAttribute(
        "class",
        `schedule-picker-chevron pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 ${selectedColorClasses.at(-1)}`,
    );

    requiredElement<HTMLButtonElement>(
        "[data-remove-schedule]",
        editScheduleForm,
    ).disabled = scheduleState.schedules.length <= 1;
};

export const initializeScheduleManagement = (
    renderSchedule: RenderPage,
): void => {
    initializeColorSelects();

    schedulePicker.addEventListener("change", () => {
        scheduleState.selectedScheduleId = schedulePicker.value;
        renderSchedule();
    });

    calendarToggle.addEventListener("change", renderSchedule);

    scheduleAddButton.addEventListener("click", () => {
        scheduleForm.reset();
        clearError(requiredElement("[data-form-error]", scheduleForm));
        scheduleDialog.showModal();
    });

    scheduleForm.addEventListener("submit", async (submitEvent) => {
        submitEvent.preventDefault();

        const errorElement = requiredElement(
            "[data-form-error]",
            scheduleForm,
        );

        clearError(errorElement);

        if (!scheduleForm.reportValidity()) {
            return;
        }

        const formData = new FormData(scheduleForm);
        const name = String(formData.get("name"));
        // A second click while this request runs would create the schedule twice.
        const createButton = requiredElement<HTMLButtonElement>(
            'button[type="submit"]',
            scheduleForm,
        );
        createButton.disabled = true;

        try {
            const schedule = await apiRequest<Schedule>("/api/schedules", {
                method: "POST",
                body: JSON.stringify({
                    name,
                    color: String(formData.get("color")),
                }),
            });

            await loadScheduleData();
            scheduleState.selectedScheduleId = schedule.id;

            scheduleDialog.close();
            renderSchedule();
        } catch (error) {
            showError(errorElement, errorMessage(error));
        } finally {
            createButton.disabled = false;
        }
    });

    scheduleEditButton.addEventListener("click", () => {
        const selectedSchedule = getSelectedSchedule();

        if (!selectedSchedule) {
            return;
        }

        formInput(editScheduleForm, "name").value = selectedSchedule.name;

        requiredElement<HTMLSelectElement>(
            'select[name="color"]',
            editScheduleForm,
        ).value = selectedSchedule.color;

        clearError(requiredElement(
            "[data-form-error]",
            editScheduleForm,
        ));

        editScheduleDialog.showModal();
    });

    editScheduleForm.addEventListener("submit", async (submitEvent) => {
        submitEvent.preventDefault();

        const errorElement = requiredElement(
            "[data-form-error]",
            editScheduleForm,
        );

        clearError(errorElement);

        if (!editScheduleForm.reportValidity()) {
            return;
        }

        const formData = new FormData(editScheduleForm);
        const name = String(formData.get("name"));
        const selectedSchedule = getSelectedSchedule();

        if (!selectedSchedule) {
            showError(errorElement, "Choose a schedule before saving.");
            return;
        }

        try {
            await apiRequest<Schedule>(
                `/api/schedules/${encodeURIComponent(selectedSchedule.id)}`,
                {
                    method: "PUT",
                    body: JSON.stringify({
                        name,
                        color: String(formData.get("color")),
                    }),
                },
            );

            await loadScheduleData();
            editScheduleDialog.close();
            renderSchedule();
        } catch (error) {
            showError(errorElement, errorMessage(error));
        }
    });

    requiredElement<HTMLButtonElement>(
        "[data-remove-schedule]",
        editScheduleForm,
    ).addEventListener("click", async () => {
        const selectedSchedule = getSelectedSchedule();

        if (!selectedSchedule || scheduleState.schedules.length <= 1) {
            return;
        }

        if (!window.confirm(
            `Remove the "${selectedSchedule.name}" schedule and all its events?`,
        )) {
            return;
        }

        clearError(requiredElement(
            "[data-form-error]",
            editScheduleForm,
        ));

        try {
            await apiRequest<void>(
                `/api/schedules/${encodeURIComponent(selectedSchedule.id)}`,
                { method: "DELETE" },
            );

            scheduleState.selectedScheduleId = "";

            await loadScheduleData();
            editScheduleDialog.close();
            renderSchedule();
        } catch (error) {
            showError(
                requiredElement("[data-form-error]", editScheduleForm),
                errorMessage(error),
            );
        }
    });
};
