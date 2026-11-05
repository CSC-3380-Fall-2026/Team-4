(() => {
// Shared DOM and dialog helpers used by the schedule page modules
const showError = (element, message) => {
    element.textContent = message;
    element.classList.remove("hidden");
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
    clearError,
    createElement,
    initializeDialogs,
});
})();
