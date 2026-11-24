function initializePlanning() {
    const picker = document.querySelector("#planning-schedule");
    const button = document.querySelector("#load-button");
    picker?.addEventListener("change", () => {
        button?.click();
    });
}
initializePlanning();
export {};
