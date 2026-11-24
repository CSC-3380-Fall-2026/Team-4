const promptKey = "tigerdrive.workday_prompt";
// Remember a new signup in this browser until its first dashboard visit,
// which may come after email confirmation in another tab.
function setPrompt(showPrompt) {
    try {
        if (showPrompt) {
            localStorage.setItem(promptKey, "1");
        }
        else {
            localStorage.removeItem(promptKey);
        }
    }
    catch {
        // Login still works when browser storage is unavailable.
    }
}
// Storage can be blocked by browser settings.
function readPrompt() {
    try {
        return localStorage.getItem(promptKey) === "1";
    }
    catch {
        return false;
    }
}
function initializeAccount() {
    const form = document.querySelector("#account-form");
    if (!form) {
        return;
    }
    // Only a successful signup offers Workday, once, not every login.
    if (form.dataset.signedUp) {
        setPrompt(true);
    }
    const password = document.querySelector("#account-password");
    const confirmation = document.querySelector("#confirm-password");
    form.addEventListener("submit", (submitEvent) => {
        if (!form.checkValidity()) {
            submitEvent.preventDefault();
            return;
        }
        if (password && confirmation) {
            confirmation.value = password.value;
        }
    });
}
// Shown only where the server can open a Workday window (not on Vercel).
async function offerWorkday(dialog) {
    try {
        const response = await fetch("/api/workday/status", {
            credentials: "same-origin",
        });
        const status = response.ok
            ? await response.json()
            : null;
        if (status?.available) {
            dialog.showModal();
        }
    }
    catch {
        // No prompt when the status can't be read.
    }
}
function initializeWorkdayPrompt() {
    const dialog = document.querySelector("#workday-dialog");
    if (!dialog) {
        return;
    }
    dialog.querySelectorAll("[data-workday-close]").forEach((button) => {
        button.addEventListener("click", () => {
            dialog.close();
        });
    });
    const connect = dialog.querySelector("#workday-connect");
    const later = dialog.querySelector(".workday-later");
    const progress = dialog.querySelector("#workday-progress-dialog");
    if (!connect || !later || !progress) {
        return;
    }
    connect.addEventListener("click", async () => {
        connect.disabled = true;
        try {
            progress.textContent = await window.tiger_workday.sync("sync", progress);
            connect.hidden = true;
            later.textContent = "Done";
            later.focus();
            // Show the imported numbers once the student closes the dialog.
            dialog.addEventListener("close", () => window.location.reload(), {
                once: true,
            });
        }
        catch (error) {
            progress.textContent = error instanceof Error
                ? error.message
                : "Workday sync failed. Please try again.";
            connect.disabled = false;
        }
    });
    const preview = new URLSearchParams(window.location.search).get("workday") === "1";
    if (readPrompt() || preview) {
        setPrompt(false);
        void offerWorkday(dialog);
    }
}
initializeAccount();
initializeWorkdayPrompt();
export {};
