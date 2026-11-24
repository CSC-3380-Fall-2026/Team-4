/** Find a required page element. */
export function requiredElement<T extends Element = HTMLElement>(
    selector: string,
    parent: ParentNode = document,
): T {
    const element = parent.querySelector<T>(selector);

    if (!element) {
        throw new Error(`Page element is missing: ${selector}`);
    }

    return element;
}

/** Find a named input in a form. */
export function formInput(
    form: HTMLFormElement,
    name: string,
): HTMLInputElement {
    const input = form.elements.namedItem(name);

    if (!(input instanceof HTMLInputElement)) {
        throw new Error(`Form input is missing: ${name}`);
    }

    return input;
}
