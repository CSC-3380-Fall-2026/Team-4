interface NoticeTimers {
    fadeInFrame: number;
    fadeOutTimer: number;
    hideTimer: number | undefined;
}

const scheduleNoticeTimers = new WeakMap<HTMLElement, NoticeTimers>();

export const showError = (
    element: Element | null,
    message: string,
): void => {
    if (!element) {
        return;
    }

    element.textContent = message;
    element.classList.remove("hidden");
};

const stopNoticeTimers = (element: HTMLElement): void => {
    const timers = scheduleNoticeTimers.get(element);

    if (!timers) {
        return;
    }

    cancelAnimationFrame(timers.fadeInFrame);
    window.clearTimeout(timers.fadeOutTimer);
    window.clearTimeout(timers.hideTimer);
    scheduleNoticeTimers.delete(element);
};

const showScheduleNotice = (element: HTMLElement): void => {
    stopNoticeTimers(element);

    if (element.matches(":popover-open")) {
        element.hidePopover();
    }

    element.style.transition = "opacity 250ms ease";
    element.style.opacity = "0";
    element.showPopover();

    const timers: NoticeTimers = {
        fadeInFrame: requestAnimationFrame(() => {
            element.style.opacity = "1";
        }),
        fadeOutTimer: window.setTimeout(() => {
            element.style.opacity = "0";

            timers.hideTimer = window.setTimeout(() => {
                if (element.matches(":popover-open")) {
                    element.hidePopover();
                }

                element.replaceChildren();
                element.style.opacity = "";
                scheduleNoticeTimers.delete(element);
            }, 250);
        }, 3250),
        hideTimer: undefined,
    };

    scheduleNoticeTimers.set(element, timers);
};

export const showScheduleConflict = (
    element: HTMLElement,
    eventNames: string[],
): void => {
    const label = createElement(
        "p",
        "text-xs font-medium",
        "Schedule Incompatibility",
    );

    const names = eventNames.length < 2
        ? eventNames[0] ?? "Another event"
        : `${eventNames.slice(0, -1).join(", ")} and ${eventNames[eventNames.length - 1]}`;

    const message = createElement(
        "p",
        "text-xl font-bold",
        `Overlapping Events: ${names}`,
    );

    element.replaceChildren(label, message);
    element.className =
        "rounded-lg border border-red-400 bg-red-200 px-3 py-2 text-red-500";
    element.setAttribute("role", "alert");
    element.setAttribute("aria-live", "assertive");

    showScheduleNotice(element);
};

export const showScheduleSuccess = (
    element: HTMLElement,
    eventName: string,
): void => {
    const label = createElement(
        "p",
        "text-xs font-medium",
        "Schedule Updated",
    );

    const message = createElement(
        "p",
        "text-xl font-bold",
        `Event Created: ${eventName}`,
    );

    element.replaceChildren(label, message);
    element.className =
        "rounded-lg border border-green-400 bg-green-100 px-3 py-2 text-green-500";
    element.setAttribute("role", "status");
    element.setAttribute("aria-live", "polite");

    showScheduleNotice(element);
};

export const clearScheduleNotice = (element: HTMLElement): void => {
    stopNoticeTimers(element);
    element.replaceChildren();

    if (element.matches(":popover-open")) {
        element.hidePopover();
    }

    element.style.opacity = "";
};

export const clearError = (element: Element | null): void => {
    if (!element) {
        return;
    }

    element.textContent = "";
    element.classList.add("hidden");
};

export const createElement = <K extends keyof HTMLElementTagNameMap>(
    tag: K,
    className?: string,
    text?: string,
): HTMLElementTagNameMap[K] => {
    const element = document.createElement(tag);

    if (className) {
        element.className = className;
    }

    if (text !== undefined) {
        element.textContent = text;
    }

    return element;
};

export const initializeDialogs = (): void => {
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
        button.addEventListener("click", () => {
            button.closest("dialog")?.close();
        });
    });
};
