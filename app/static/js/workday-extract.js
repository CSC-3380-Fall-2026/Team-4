// Reads every grid on an LSU Workday page; run it with Playwright's page.evaluate().
// Returns [{semester, title, rows}] where semester is the nearest section
// heading above the grid (or null), title is the grid's own title (or ""),
// and rows are {column header: visible cell text}. Merged cells are copied
// into every row they cover, so a lab row under its lecture comes out complete.
() => {
    "use strict";

    // Visible text only: screen-reader labels and hidden nodes are skipped.
    function visible_text(element) {
        const parts = [];
        const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            const parent = node.parentElement;
            const hidden = parent.closest('[data-automation-id="screenReader"]') || !parent.checkVisibility();
            if (!hidden) {
                parts.push(node.nodeValue);
            }
        }
        return parts.join(" ").replace(/\s+/g, " ").trim();
    }

    // Copy one cell's text into every grid slot it spans.
    function place_cell(grid, top, column, cell) {
        const text = visible_text(cell);
        for (let down = 0; down < cell.rowSpan; down++) {
            const row = (grid[top + down] ??= []);
            for (let across = 0; across < cell.colSpan; across++) {
                row[column + across] = text;
            }
        }
    }

    // Lay table rows out as a grid of cell texts.
    function cell_grid(rows) {
        const grid = [];
        rows.forEach((row, top) => {
            grid[top] ??= [];
            let column = 0;
            for (const cell of row.cells) {
                while (grid[top][column] !== undefined) {
                    column++;
                }
                place_cell(grid, top, column, cell);
                column += cell.colSpan;
            }
        });
        return grid;
    }

    const headings = [...document.querySelectorAll('h4[data-automation-id="fieldSetLegendHeading"]')];

    function semester_of(table) {
        const above = headings.filter(
            (heading) => heading.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING
        );
        return above.at(-1)?.innerText ?? null;
    }

    function title_of(table) {
        const widget = table.closest('[data-automation-id="rivaWidget"]');
        return widget?.querySelector('[data-automation-id="gridTitleLabel"]')?.innerText ?? "";
    }

    function read_table(table) {
        const headers = cell_grid([...table.querySelectorAll("thead tr")]).at(-1) ?? [];
        const rows = cell_grid([...table.querySelectorAll("tbody tr")]);
        return {
            semester: semester_of(table),
            title: title_of(table),
            rows: rows.map((cells) => Object.fromEntries(headers.map((header, index) => [header, cells[index] ?? ""]))),
        };
    }

    return [...document.querySelectorAll('table[data-automation-id="table"]')].map(read_table);
}
