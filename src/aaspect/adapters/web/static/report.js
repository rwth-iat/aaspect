"use strict";

// While an analysis runs, the page asks the server whether a step has finished and
// reloads only then, so it stays still while being read. Folded sections are remembered
// for the tab, so a reload does not unfold them.
const POLL_MILLISECONDS = 2000;

function foldedKey(report) {
  return `aaspect-folded:${report}`;
}

function readFolded(storage, report) {
  try {
    return new Set(JSON.parse(storage.getItem(foldedKey(report)) || "[]"));
  } catch {
    return new Set();
  }
}

function rememberFolds(root, storage) {
  const report = root.dataset.key;
  const sections = Array.from(root.querySelectorAll("details[data-section]"));
  const folded = readFolded(storage, report);
  for (const details of sections) {
    if (folded.has(details.dataset.section)) details.open = false;
    details.addEventListener("toggle", () => {
      const now = sections.filter((d) => !d.open).map((d) => d.dataset.section);
      try {
        storage.setItem(foldedKey(report), JSON.stringify(now));
      } catch {
        // Storage can be blocked or full; folding still works, it is just not kept.
      }
    });
  }
}

// `check` resolves to true when the page should reload, false to keep polling, and
// null to stop (report finished or gone).
async function check(fetchStatus, report, state) {
  const response = await fetchStatus(`/reports/${encodeURIComponent(report)}/status`);
  if (!response.ok) return null;
  const status = await response.json();
  if (status.state !== state) return true;
  return status.finished ? null : false;
}

function poll(root, fetchStatus, reload, schedule) {
  const step = () => {
    check(fetchStatus, root.dataset.key, root.dataset.state).then(
      (outcome) => {
        if (outcome === true) reload();
        else if (outcome === false) schedule(step, POLL_MILLISECONDS);
      },
      () => schedule(step, POLL_MILLISECONDS),
    );
  };
  schedule(step, POLL_MILLISECONDS);
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => {
    const root = document.getElementById("report");
    if (!root) return;
    try {
      rememberFolds(root, window.sessionStorage);
    } catch {
      // Without storage (blocked in some private modes) folds are not kept across reloads.
    }
    if (root.dataset.finished !== "true") {
      poll(
        root,
        (url) => fetch(url, { cache: "no-store" }),
        () => window.location.reload(),
        (step, delay) => window.setTimeout(step, delay),
      );
    }
  });
}
if (typeof module !== "undefined") {
  module.exports = { check, readFolded };
}
