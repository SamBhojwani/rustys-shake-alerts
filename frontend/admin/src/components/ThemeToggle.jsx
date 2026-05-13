import { useEffect, useState } from 'react';
import { getTheme, setTheme } from '../theme';

/**
 * Two-state sun ↔ moon switch.
 * On first visit the resolved mode follows the OS preference (no
 * localStorage entry yet); first click promotes that to an explicit
 * choice and persists it.
 */
export default function ThemeToggle() {
  const [isDark, setIsDark] = useState(() => resolveIsDark());

  // Keep the switch in sync if the OS preference flips while the user
  // hasn't picked an explicit theme yet.
  useEffect(() => {
    if (getTheme() !== 'system') return;
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const update = () => setIsDark(mql.matches);
    mql.addEventListener('change', update);
    return () => mql.removeEventListener('change', update);
  }, []);

  function toggle() {
    const next = isDark ? 'light' : 'dark';
    setTheme(next);
    setIsDark(!isDark);
  }

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isDark}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      className="theme-switch"
      onClick={toggle}
    >
      <SunIcon />
      <MoonIcon />
      <span className="thumb" aria-hidden="true" />
    </button>
  );
}

function resolveIsDark() {
  const saved = getTheme();
  if (saved === 'dark') return true;
  if (saved === 'light') return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function SunIcon() {
  return (
    <svg
      className="icon icon-sun"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <circle cx="8" cy="8" r="2.6" />
      <path d="M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M3.4 12.6l1.1-1.1M11.5 4.5l1.1-1.1" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      className="icon icon-moon"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M13.2 9.3a5.6 5.6 0 1 1-6.5-7 4.5 4.5 0 0 0 6.5 7z" />
    </svg>
  );
}
