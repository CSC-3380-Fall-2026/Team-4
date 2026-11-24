(() => {
    "use strict";

    const prompt_key = "tigerdrive.workday_prompt";
    const account_form = document.querySelector("#account-form");
    const workday_dialog = document.querySelector("#workday-dialog");

    // Remember a new signup in this browser until its first dashboard visit,
    // which may come after email confirmation in another tab.
    function set_prompt(show_prompt) {
        try {
            if (show_prompt) {
                localStorage.setItem(prompt_key, "1");
            } else {
                localStorage.removeItem(prompt_key);
            }
        } catch {
            // Login still works when browser storage is unavailable.
        }
    }

    // Storage can be blocked by browser settings.
    function read_prompt() {
        try {
            return localStorage.getItem(prompt_key) === "1";
        } catch {
            return false;
        }
    }

    if (account_form) {
        // Only a successful signup offers Workday, once, not every login.
        if (account_form.dataset.signedUp) {
            set_prompt(true);
        }

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

    const connect = workday_dialog.querySelector("#workday-connect");
    const later = workday_dialog.querySelector(".workday-later");
    const progress = workday_dialog.querySelector("#workday-progress-dialog");

    connect.addEventListener("click", async () => {
        connect.disabled = true;
        try {
            progress.textContent = await window.tiger_workday.sync("sync", progress);
            connect.hidden = true;
            later.textContent = "Done";
            later.focus();
            // Show the imported numbers once the student closes the dialog.
            workday_dialog.addEventListener("close", () => window.location.reload(), { once: true });
        } catch (error) {
            progress.textContent = error.message;
            connect.disabled = false;
        }
    });

    const query = new URLSearchParams(window.location.search);
    const preview = query.get("workday") === "1";

    // Shown only where the server can open a Workday window (not on Vercel).
    async function offer() {
        try {
            const response = await fetch("/api/workday/status", { credentials: "same-origin" });
            const status = response.ok ? await response.json() : null;
            if (status?.available) {
                workday_dialog.showModal();
            }
        } catch {
            // No prompt when the status can't be read.
        }
    }

    if (read_prompt() || preview) {
        set_prompt(false);
        offer();
    }
})();
