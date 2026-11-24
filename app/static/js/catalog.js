function initializeCatalog() {
    const category = document.querySelector("#category");
    category?.addEventListener("change", () => {
        category.form?.requestSubmit();
    });
}
initializeCatalog();
export {};
