/** Find a required page element. */
export function requiredElement(selector, parent = document) {
    const element = parent.querySelector(selector);
    if (!element) {
        throw new Error(`Page element is missing: ${selector}`);
    }
    return element;
}
/** Find a named input in a form. */
export function formInput(form, name) {
    const input = form.elements.namedItem(name);
    if (!(input instanceof HTMLInputElement)) {
        throw new Error(`Form input is missing: ${name}`);
    }
    return input;
}
