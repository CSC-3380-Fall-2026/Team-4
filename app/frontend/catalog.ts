function initializeCatalog(): void {
    const category = document.querySelector<HTMLSelectElement>(
        "#category",
    );

    category?.addEventListener("change", () => {
        category.form?.requestSubmit();
    });
}

initializeCatalog();

export {};
