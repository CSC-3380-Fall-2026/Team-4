function initializePlanning(): void {
    const picker = document.querySelector<HTMLSelectElement>(
        "#planning-schedule",
    );

    const button = document.querySelector<HTMLButtonElement>(
        "#load-button",
    );

    picker?.addEventListener("change", () => {
        button?.click();
    });
}

initializePlanning();

export {};
