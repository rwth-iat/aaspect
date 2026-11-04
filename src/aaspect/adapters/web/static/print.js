"use strict";

// A browser prints a folded part without its content; on paper everything is open, and
// the folds come back afterward.
function openForPrint(root, win) {
  let opened = [];
  win.addEventListener("beforeprint", () => {
    opened = Array.from(root.querySelectorAll("details:not([open])"));
    for (const details of opened) details.open = true;
  });
  win.addEventListener("afterprint", () => {
    for (const details of opened) details.open = false;
    opened = [];
  });
}

if (typeof document !== "undefined") openForPrint(document, window);
if (typeof module !== "undefined") {
  module.exports = { openForPrint };
}
