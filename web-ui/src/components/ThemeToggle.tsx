import { useTheme } from '../hooks/useTheme';
import './ThemeToggle.css';

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="theme-toggle">
      <button
        className={theme === 'light' ? 'active' : ''}
        onClick={() => setTheme('light')}
        aria-label="Light mode"
      >
        ☀️
      </button>
      <button
        className={theme === 'dark' ? 'active' : ''}
        onClick={() => setTheme('dark')}
        aria-label="Dark mode"
      >
        🌙
      </button>
      <button
        className={theme === 'system' ? 'active' : ''}
        onClick={() => setTheme('system')}
        aria-label="System preference"
      >
        💻
      </button>
    </div>
  );
}
