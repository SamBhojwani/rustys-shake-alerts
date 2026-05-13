// ═══════════════════════════════════════════════════════════════════
// Theme module
// Resolves to: 'system' (follows OS) | 'light' | 'dark'.
// Persists choice in localStorage; CSS handles the OS-driven default.
// ═══════════════════════════════════════════════════════════════════

const STORAGE_KEY = 'rusty.theme';
const VALID = new Set(['system', 'light', 'dark']);

function readStored() {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return VALID.has(v) ? v : 'system';
  } catch {
    return 'system';
  }
}

function writeStored(mode) {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
}

export function applyTheme(mode) {
  const html = document.documentElement;
  if (mode === 'system') {
    html.removeAttribute('data-theme');
  } else {
    html.setAttribute('data-theme', mode);
  }
}

export function getTheme() {
  return readStored();
}

export function setTheme(mode) {
  const next = VALID.has(mode) ? mode : 'system';
  writeStored(next);
  applyTheme(next);
  window.dispatchEvent(new CustomEvent('rusty:theme', { detail: next }));
  return next;
}

export function initTheme() {
  applyTheme(readStored());
}

export function onThemeChange(handler) {
  const listener = (e) => handler(e.detail);
  window.addEventListener('rusty:theme', listener);
  return () => window.removeEventListener('rusty:theme', listener);
}
