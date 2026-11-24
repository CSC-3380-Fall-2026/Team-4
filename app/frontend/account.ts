function initializeAccount(): void {
    const form = document.querySelector<HTMLFormElement>(
        "#account-form",
    );

    const password = document.querySelector<HTMLInputElement>(
        "#account-password",
    );

    const confirmation = document.querySelector<HTMLInputElement>(
        "#confirm-password",
    );

    if (form && password && confirmation) {
        form.addEventListener("submit", () => {
            confirmation.value = password.value;
        });
    }
}

initializeAccount();

export {};
