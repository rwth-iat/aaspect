"use strict";

// Follows the system's light or dark setting until the switch is used; the choice is
// kept per browser. Loaded in <head> without defer so a kept choice applies before the
// first paint.
const THEME_KEY = "aaspect-theme";

function systemTheme() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function keptTheme() {
  try {
    const theme = window.localStorage.getItem(THEME_KEY);
    return theme === "light" || theme === "dark" ? theme : null;
  } catch {
    return null;
  }
}

function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
}

function label(button) {
  const current = document.documentElement.dataset.theme || systemTheme();
  button.textContent = current === "dark" ? "Light mode" : "Dark mode";
}

applyTheme(keptTheme());
document.addEventListener("DOMContentLoaded", () => {
  const button = document.getElementById("theme-switch");
  if (!button) return;
  button.hidden = false;
  label(button);
  button.addEventListener("click", () => {
    const next = (document.documentElement.dataset.theme || systemTheme()) === "dark" ? "light" : "dark";
    applyTheme(next);
    try {
      window.localStorage.setItem(THEME_KEY, next);
    } catch {
      // Without storage the choice holds for this page only.
    }
    label(button);
  });
});
