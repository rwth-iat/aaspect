"use strict";

// Long tables and lists render in full, so they read without JavaScript and print whole.
// With it, rows past the first few are hidden behind one button below the same table,
// which reveals them in place instead of opening a second table.
const SHOWN_ROWS = 10;

function collapse(container) {
  const rows = Array.from(container.querySelectorAll(":scope > tr, :scope > li"));
  // data-collapse="50" keeps more rows open where a page is about the list itself.
  const shown = Number.parseInt(container.dataset.collapse, 10) || SHOWN_ROWS;
  if (rows.length <= shown + 2) return;
  const extra = rows.slice(shown);
  for (const row of extra) {
    row.classList.add("extra");
    row.hidden = true;
  }
  const button = document.createElement("button");
  button.type = "button";
  button.className = "show-more";
  button.textContent = `Show all ${rows.length} rows`;
  button.addEventListener("click", () => {
    const hide = !extra[0].hidden;
    for (const row of extra) row.hidden = hide;
    button.textContent = hide ? `Show all ${rows.length} rows` : `Show the first ${shown} only`;
  });
  const anchor = container.closest(".table-wrap") || container;
  anchor.after(button);
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => {
    for (const container of document.querySelectorAll("[data-collapse]")) collapse(container);
  });
}
