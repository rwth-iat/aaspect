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

// Directory names end in "/" so that siblings sort as their full paths do: "a.json" comes
// before "a/x.json" because "." sorts before "/".
function sortKey(handle) {
  return handle.kind === "directory" ? `${handle.name}/` : handle.name;
}

function byKey(a, b) {
  const [x, y] = [sortKey(a), sortKey(b)];
  if (x === y) return 0;
  return x < y ? -1 : 1;
}

// A folder chosen with the browser's folder input is listed in full before the page sees
// any of it, which takes minutes for a folder of 200,000 files. Where the browser offers
// showDirectoryPicker, the folder is read in path order instead, and reading stops once a
// limit is reached. `progress` gets the number of files kept so far.
async function readFolder(root, maxFiles, maxBytes, progress) {
  const kept = [];
  let bytes = REQUEST_OVERHEAD;
  async function walk(directory, path) {
    const children = [];
    try {
      for await (const child of directory.values()) children.push(child);
    } catch {
      return true; // A subfolder the browser may not read is left out, like a locked file.
    }
    for (const child of children.sort(byKey)) {
      const childPath = `${path}/${child.name}`;
      if (child.kind === "directory") {
        if (!(await walk(child, childPath))) return false;
      } else if (isAasFile(child)) {
        let file;
        try {
          file = await child.getFile();
        } catch {
          continue;
        }
        const cost = file.size + PER_FILE_OVERHEAD;
        if (kept.length >= maxFiles || bytes + cost > maxBytes) return false;
        kept.push({ name: child.name, path: childPath, size: file.size, file });
        bytes += cost;
        progress(kept.length);
      }
    }
    return true;
  }
  const complete = await walk(root, root.name);
  return { entries: kept, complete };
}

function entries(input, fromFolder) {
  return Array.from(input.files, (file) => ({
    name: file.name,
    path: fromFolder && file.webkitRelativePath ? file.webkitRelativePath : file.name,
    size: file.size,
    file,
  }));
}

// `folderComplete` is false when reading a folder stopped at a limit, so the number of
// files it holds is not known.
function summary(selection, maxFiles, maxBytes, folderComplete = true) {
  const megabytes = Math.floor(maxBytes / 2 ** 20);
  if (!folderComplete) {
    return (
      `${selection.chosen.length} files will be analyzed; the folder holds more ` +
      `(limit: ${maxFiles} files, ${megabytes} MB).`
    );
  }
  if (selection.total === 0) return "";
  if (selection.chosen.length === selection.total) {
    return `${selection.total} ${selection.total === 1 ? "file" : "files"} will be analyzed.`;
  }
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
  const button = form.querySelector('button[type="submit"]');
  const label = button.textContent;
  // A folder read with showDirectoryPicker: its entries, and whether it was read to the end.
  let read = null;
  let reading = false;
  // A second click would start a second analysis while the browser waits for the first;
  // the server keeps running both, and a third finds no free slot.
  let submitted = false;
  // Inside another page Chromium refuses the picker, and in Electron apps such as VS Code's
  // browser view it opens but never returns the folder; the folder input works in both.
  let pickerRefused = false;
  const electron = typeof navigator !== "undefined" && /\bElectron\//.test(navigator.userAgent);
  const usePicker = () =>
    typeof window.showDirectoryPicker === "function" &&
    window.self === window.top &&
    !electron &&
    !pickerRefused;
  const folderEntries = () => (read ? read.entries : entries(folderInput, true));
  const current = () =>
    selectFiles(entries(filesInput, false), folderEntries(), maxFiles, maxBytes);

  const show = () => {
    notice.textContent = summary(current(), maxFiles, maxBytes, read ? read.complete : true);
  };
  filesInput.addEventListener("change", show);
  folderInput.addEventListener("change", () => {
    read = null;
    show();
  });
  folderInput.addEventListener("cancel", show);
  folderInput.addEventListener("click", (event) => {
    if (!usePicker()) {
      notice.textContent = "Reading the folder… a large folder takes a while.";
      return;
    }
    event.preventDefault();
    chooseFolder();
  });

  async function chooseFolder() {
    let root;
    try {
      root = await window.showDirectoryPicker();
    } catch (error) {
      if (error && error.name === "AbortError") return; // Cancelled.
      // Refused by the browser: open the folder input instead, now and from now on.
      pickerRefused = true;
      folderInput.click();
      return;
    }
    reading = true;
    button.disabled = true;
    notice.textContent = "Reading the folder…";
    try {
      read = await readFolder(root, maxFiles, maxBytes, (count) => {
        notice.textContent = `Reading the folder… ${count} files so far.`;
      });
      folderInput.value = "";
      show();
    } catch {
      read = null;
      notice.textContent = "The folder could not be read.";
    } finally {
      reading = false;
      button.disabled = submitted;
    }
  }
  window.addEventListener("pageshow", () => {
    // Coming back with the Back button restores the page as it was left: disabled.
    submitted = false;
    button.disabled = false;
    button.textContent = label;
  });

  form.addEventListener("submit", (event) => {
    if (submitted || reading) {
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
  module.exports = { readFolder, selectFiles, setUp, summary };
}
