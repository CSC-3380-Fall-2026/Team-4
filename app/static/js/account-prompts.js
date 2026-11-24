(() => {
    "use strict";

    const prompt_key = "tigerdrive.workday_prompt";
    const account_form = document.querySelector("#account-form");
    const workday_dialog = document.querySelector("#workday-dialog");

    // Keep the pending prompt in this browser tab only.
    function set_prompt(show_prompt) {
        try {
            if (show_prompt) {
                sessionStorage.setItem(prompt_key, "1");
            } else {
                sessionStorage.removeItem(prompt_key);
            }
        } catch {
            // Login still works when browser storage is unavailable.
        }
    }

    // Storage can be blocked by browser settings.
    function read_prompt() {
        try {
            return sessionStorage.getItem(prompt_key) === "1";
        } catch {
            return false;
        }
    }

    if (account_form) {
        // A login or signup form cancels any earlier login attempt.
        set_prompt(false);

        account_form.addEventListener("submit", (event) => {
            if (!account_form.checkValidity()) {
                event.preventDefault();
                return;
            }

            const password = account_form.querySelector("#account-password");
            const confirmation = account_form.querySelector("#confirm-password");

            if (confirmation) {
                confirmation.value = password.value;
            }

            if (account_form.dataset.mode === "login") {
                set_prompt(true);
            }
        });
    }

    if (!workday_dialog) {
        return;
    }

    workday_dialog.querySelectorAll("[data-workday-close]").forEach((button) => {
        button.addEventListener("click", () => {
            workday_dialog.close();
        });
    });

    const workday_link = workday_dialog.querySelector("#workday-open");

    workday_link.addEventListener("click", () => {
        workday_dialog.close();
    });

    const query = new URLSearchParams(window.location.search);
    const preview = query.get("workday") === "1";

    if (read_prompt() || preview) {
        set_prompt(false);
        workday_dialog.showModal();
    }
})();
