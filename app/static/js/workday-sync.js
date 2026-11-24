(() => {
    "use strict";

    const done_key = "tigerdrive.workday_done";

    function plural(count, one, many) {
        return `${count} ${count === 1 ? one : many}`;
    }

    // Say in one sentence what a sync saved.
    function summary(data) {
        const parts = [
            data.gpa === null ? "no GPA yet" : `GPA ${data.gpa.toFixed(2)}`,
            `${data.completed_credit_hours} credit hours`,
            `${plural(data.courses_added, "course", "courses")} added to your profile`,
        ];
        if (data.schedule) {
            const where = data.schedule_created ? "the new schedule" : "the schedule";
            parts.push(`${plural(data.classes_added, "class", "classes")} added to ${where} “${data.schedule}”`);
        }
        return `Imported from Workday: ${parts.join(", ")}.`;
    }

    // Run a sync ("sync" or "reset"); resolves to a summary, rejects with a readable message.
    async function sync_workday(path, progress) {
        progress.textContent = "A Chromium window opened — sign in to Workday there. "
            + "This page updates when the sync finishes.";
        progress.focus();

        let response;
        try {
            response = await fetch(`/api/workday/${path}`, {
                method: "POST",
                credentials: "same-origin",
            });
        } catch {
            throw new Error("The app could not be reached. Check that it is still running, then try again.");
        }

        let data = null;
        try {
            data = await response.json();
        } catch {
            data = null;
        }
        if (!response.ok) {
            const detail = typeof data?.detail === "string" ? data.detail : "";
            throw new Error(detail || "Workday sync failed. Please try again.");
        }
        return summary(data);
    }

    window.tiger_workday = { sync: sync_workday };

    // ---------- profile page card ----------
    const card = document.querySelector("#workday-card");
    if (!card) {
        return;
    }

    const progress = card.querySelector("#workday-progress");
    const buttons = [...card.querySelectorAll("button")];

    card.querySelectorAll("time[datetime]").forEach((time) => {
        time.textContent = new Date(time.dateTime).toLocaleString();
    });

    // The page reloads after a sync, so the result is carried over in this tab.
    try {
        const note = sessionStorage.getItem(done_key);
        if (note) {
            sessionStorage.removeItem(done_key);
            progress.textContent = note;
            progress.focus();
        }
    } catch {
        // Storage can be blocked; the reloaded page still shows the new data.
    }

    async function run(path) {
        buttons.forEach((button) => {
            button.disabled = true;
        });
        try {
            const note = await sync_workday(path, progress);
            try {
                sessionStorage.setItem(done_key, note);
            } catch {
                // See above.
            }
            // Reload so the course list in the form shows what was saved.
            window.location.reload();
        } catch (error) {
            progress.textContent = error.message;
            buttons.forEach((button) => {
                button.disabled = false;
            });
        }
    }

    card.querySelector("#workday-sync").addEventListener("click", () => run("sync"));

    card.querySelector("#workday-reset")?.addEventListener("click", () => {
        const sure = window.confirm(
            "Replace all your saved courses with the ones in Workday? "
            + "Courses you added or edited by hand will be removed."
        );
        if (sure) {
            run("reset");
        }
    });
})();
