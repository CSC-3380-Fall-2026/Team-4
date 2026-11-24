export function makeElement(tag, classes, text) {
    const element = document.createElement(tag);
    element.className = classes;
    if (text !== undefined) {
        element.textContent = text;
    }
    return element;
}
