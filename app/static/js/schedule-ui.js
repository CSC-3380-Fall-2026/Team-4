(() => {
// Shared DOM and dialog helpers used by the schedule page modules
const scheduleNoticeTimers = new WeakMap();

const showError = (element, message) => {
    element.textContent = message;
    element.classList.remove("hidden");
};

// Construct pop up for schedule events
const showScheduleNotice = (element) => {
    const previousTimers = scheduleNoticeTimers.get(element);
    if (previousTimers) {
        cancelAnimationFrame(previousTimers.fadeInFrame);
        clearTimeout(previousTimers.fadeOutTimer);
        clearTimeout(previousTimers.hideTimer);
    }
    if (element.matches(":popover-open")) {
        element.hidePopover();
    }

    element.style.transition = "opacity 250ms ease";
    element.style.opacity = "0";
    element.showPopover();

    const timers = {
        fadeInFrame: requestAnimationFrame(() => {
            element.style.opacity = "1";
        }),
        fadeOutTimer: setTimeout(() => {
            element.style.opacity = "0";
            timers.hideTimer = setTimeout(() => {
                if (element.matches(":popover-open")) {
                    element.hidePopover();
                }
                element.replaceChildren();
                element.style.opacity = "";
                scheduleNoticeTimers.delete(element);
            }, 250);
        }, 3250),
        hideTimer: null,
    };
    scheduleNoticeTimers.set(element, timers);
};

// Construct error message for event time conflicts
const showScheduleConflict = (element, eventNames) => {
    const label = createElement("p", "text-xs font-medium", "Schedule Incompatibility");
    const formatNames = (names) => names.length < 2
        ? names[0]
        : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
    const message = createElement(
        "p",
        "text-xl font-bold",
        `Overlapping Events: ${formatNames(eventNames)}`,
    );
    element.replaceChildren(label, message);
    element.className = "rounded-lg border border-red-400 bg-red-200 px-3 py-2 text-red-500";
    element.setAttribute("role", "alert");
    element.setAttribute("aria-live", "assertive");
    showScheduleNotice(element);
};

//Construct success message for when event is added
const showScheduleSuccess = (element, eventName) => {
    const label = createElement("p", "text-xs font-medium", "Schedule Updated");
    const message = createElement("p", "text-xl font-bold", `Event Created: ${eventName}`);
    element.replaceChildren(label, message);
    element.className = "rounded-lg border border-green-400 bg-green-100 px-3 py-2 text-green-500";
    element.setAttribute("role", "status");
    element.setAttribute("aria-live", "polite");
    showScheduleNotice(element);
};

// Hide error popup
const clearScheduleNotice = (element) => {
    const timers = scheduleNoticeTimers.get(element);
    if (timers) {
        cancelAnimationFrame(timers.fadeInFrame);
        clearTimeout(timers.fadeOutTimer);
        clearTimeout(timers.hideTimer);
        scheduleNoticeTimers.delete(element);
    }
    element.replaceChildren();
    if (element.matches(":popover-open")) {
        element.hidePopover();
    }
    element.style.opacity = "";
};

const clearError = (element) => {
    element.textContent = "";
    element.classList.add("hidden");
};

const createElement = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) {
        element.className = className;
    }
    if (text !== undefined) {
        element.textContent = text;
    }
    return element;
};

const initializeDialogs = () => {
    // Close dialogs only when a click is on blurred backdrop outside the dialog
    document.querySelectorAll("dialog").forEach((dialog) => {
        dialog.addEventListener("click", (clickEvent) => {
            if (clickEvent.target !== dialog) {
                return;
            }

            const bounds = dialog.getBoundingClientRect();
            const isOutsideDialog =
                clickEvent.clientX < bounds.left
                || clickEvent.clientX > bounds.right
                || clickEvent.clientY < bounds.top
                || clickEvent.clientY > bounds.bottom;

            if (isOutsideDialog) {
                dialog.close();
            }
        });
    });

    document.querySelectorAll("[data-dialog-cancel]").forEach((button) => {
        button.addEventListener("click", () => button.closest("dialog").close());
    });
};

Object.assign(window.SchedulePrototype, {
    showError,
    showScheduleConflict,
    showScheduleSuccess,
    clearScheduleNotice,
    clearError,
    createElement,
    initializeDialogs,
});
})();
