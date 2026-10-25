"use strict";

// A chosen folder is sent file by file. Without trimming, the browser would send all of
// it and the server would reject anything over its limits, so the selection keeps AAS
// files only and stops at the limits before anything is sent.
const AAS_EXTENSIONS = [".aasx", ".json", ".xml"];
// Multipart framing adds bytes per file and per request on top of the file contents.
const PER_FILE_OVERHEAD = 512;
const REQUEST_OVERHEAD = 4096;

function isAasFile(entry) {
  const name = entry.name.toLowerCase();
  return AAS_EXTENSIONS.some((extension) => name.endsWith(extension));
}

function byPath(a, b) {
  if (a.path === b.path) return 0;
  return a.path < b.path ? -1 : 1;
}

// Files picked one by one are kept as they are; folder files are filtered and sorted.
function selectFiles(picked, folder, maxFiles, maxBytes) {
  const candidates = [...picked, ...folder.filter(isAasFile).sort(byPath)];
  const chosen = [];
  let bytes = REQUEST_OVERHEAD;
  for (const entry of candidates) {
    const cost = entry.size + PER_FILE_OVERHEAD;
    if (chosen.length >= maxFiles || bytes + cost > maxBytes) break;
    chosen.push(entry);
    bytes += cost;
  }
  return { chosen, total: candidates.length };
}

function entries(input, fromFolder) {
  return Array.from(input.files, (file) => ({
    name: file.name,
    path: fromFolder && file.webkitRelativePath ? file.webkitRelativePath : file.name,
    size: file.size,
    file,
  }));
}

function summary(selection, maxFiles, maxBytes) {
  if (selection.total === 0) return "";
  if (selection.chosen.length === selection.total) {
    return `${selection.total} ${selection.total === 1 ? "file" : "files"} will be analyzed.`;
  }
  const megabytes = Math.floor(maxBytes / 2 ** 20);
  return (
    `${selection.chosen.length} of ${selection.total} files will be analyzed ` +
    `(limit: ${maxFiles} files, ${megabytes} MB).`
  );
}

function setUp(form) {
  const filesInput = form.querySelector("#files");
  const folderInput = form.querySelector("#folder");
  const notice = form.querySelector("#selection");
  const maxFiles = Number(form.dataset.maxFiles);
  const maxBytes = Number(form.dataset.maxBytes);
  const current = () =>
    selectFiles(entries(filesInput, false), entries(folderInput, true), maxFiles, maxBytes);

  const show = () => {
    notice.textContent = summary(current(), maxFiles, maxBytes);
  };
  filesInput.addEventListener("change", show);
  folderInput.addEventListener("change", show);

  // A second click would start a second analysis while the browser waits for the first;
  // the server keeps running both, and a third finds no free slot.
  const button = form.querySelector('button[type="submit"]');
  const label = button.textContent;
  let submitted = false;
  window.addEventListener("pageshow", () => {
    // Coming back with the Back button restores the page as it was left: disabled.
    submitted = false;
    button.disabled = false;
    button.textContent = label;
  });

  form.addEventListener("submit", (event) => {
    if (submitted) {
      event.preventDefault();
      return;
    }
    submitted = true;
    button.disabled = true;
    button.textContent = "Analyzing…";
    const transfer = new DataTransfer();
    for (const entry of current().chosen) {
      // The path inside the folder becomes the name, so equal names in different
      // subfolders stay apart in the report.
      const file =
        entry.path === entry.name
          ? entry.file
          : new File([entry.file], entry.path, { type: entry.file.type });
      transfer.items.add(file);
    }
    filesInput.files = transfer.files;
    folderInput.value = "";
  });
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("form[data-max-files]");
    if (form) setUp(form);
  });
}
if (typeof module !== "undefined") {
  module.exports = { selectFiles, setUp, summary };
}
