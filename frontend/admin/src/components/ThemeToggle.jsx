import { useEffect, useState } from 'react';
import { getTheme, setTheme } from '../theme';

/**
 * Three-state pill: System / Light / Dark.
 * System follows the OS preference via CSS media query.
 */
export default function ThemeToggle({ className = '' }) {
  const [mode, setMode] = useState(() => getTheme());

  useEffect(() => {
    setMode(getTheme());
  }, []);

  function choose(next) {
    setTheme(next);
    setMode(next);
  }

  const options = [
    { id: 'system', label: 'Auto' },
    { id: 'light', label: 'Light' },
    { id: 'dark', label: 'Dark' },
  ];

  return (
    <div
      className={`theme-toggle ${className}`}
      role="group"
      aria-label="Color theme"
    >
      {options.map((opt) => (
        <button
          key={opt.id}
          type="button"
          className={mode === opt.id ? 'on' : ''}
          onClick={() => choose(opt.id)}
          aria-pressed={mode === opt.id}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
