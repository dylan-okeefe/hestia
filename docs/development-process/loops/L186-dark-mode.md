# L186 — Dark Mode

**Status:** Spec only  
**Branch:** `feature/l186-dark-mode` (from `feature/l179-rooms-interactive-nodes`)  
**Depends on:** L184 (shared CSS system), L185 (responsive design)

## Intent

The web UI currently has no dark mode. All colors are hardcoded as light-theme values (white backgrounds, dark text, light gray borders). Adding dark mode requires:
1. A dark color palette
2. A toggle mechanism
3. Per-color-component updates for any hardcoded colors that don't use CSS variables
4. Testing that all pages look correct in both themes

This loop adds a complete dark mode to the web UI.

## Scope

### §0 — Add dark color tokens

**Why:** L184 created light tokens. We need matching dark tokens.

In `web-ui/src/styles/variables.css`, add a `data-theme="dark"` section:

```css
[data-theme="dark"] {
  --color-bg: #0f0f0f;
  --color-surface: #1a1a1a;
  --color-surface-raised: #1f1f1f;
  --color-border: #2a2a2a;
  --color-border-subtle: #222222;
  --color-text: #f0f0f0;
  --color-text-secondary: #a0a0a0;
  --color-text-muted: #707070;
  --color-primary: #3b82f6;
  --color-primary-hover: #60a5fa;
  --color-danger: #ef4444;
  --color-danger-hover: #f87171;
  --color-success: #22c55e;
  --color-warning: #eab308;

  /* Shadows need to be visible on dark backgrounds */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
  --shadow-md: 0 2px 8px rgba(0, 0, 0, 0.4);
  --shadow-lg: 0 4px 16px rgba(0, 0, 0, 0.5);
}
```

**Commit:** `feat(web-ui): add dark color tokens`

### §1 — Create theme provider and toggle

**Why:** Theme state needs to be global, persisted, and accessible to all components.

In `web-ui/src/hooks/useTheme.ts`:

```typescript
import { useState, useEffect, useCallback } from 'react';

type Theme = 'light' | 'dark' | 'system';

const STORAGE_KEY = 'hestia-theme';

function getSystemTheme(): 'light' | 'dark' {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function getInitialTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
  return stored || 'system';
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme);

  const effectiveTheme = theme === 'system' ? getSystemTheme() : theme;

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', effectiveTheme);
  }, [effectiveTheme]);

  const setTheme = useCallback((newTheme: Theme) => {
    localStorage.setItem(STORAGE_KEY, newTheme);
    setThemeState(newTheme);
  }, []);

  return { theme, effectiveTheme, setTheme };
}
```

In `web-ui/src/components/ThemeToggle.tsx`:

```typescript
import { useTheme } from '../hooks/useTheme';

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
```

In `web-ui/src/components/ThemeToggle.css`:

```css
.theme-toggle {
  display: flex;
  gap: var(--space-1);
  padding: var(--space-1);
  background: var(--color-surface);
  border-radius: var(--radius-md);
  border: var(--border-thin);
}

.theme-toggle button {
  padding: var(--space-1) var(--space-2);
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.theme-toggle button:hover {
  color: var(--color-text);
}

.theme-toggle button.active {
  background: var(--color-surface-raised);
  color: var(--color-text);
  box-shadow: var(--shadow-sm);
}
```

Place the `ThemeToggle` in the sidebar (desktop) or in the mobile top bar (hamburger menu).

**Commit:** `feat(web-ui): theme provider and toggle component`

### §2 — Audit and fix hardcoded colors

**Why:** Some components may use inline colors that bypass CSS variables. These will look wrong in dark mode.

1. Search for hardcoded color values in all `.css` and `.tsx` files:
   ```bash
   grep -r "#fff\|#ffffff\|#000\|#000000\|rgb(0\|rgba(0" web-ui/src/
   grep -r "background.*#\|color.*#\|border.*#" web-ui/src/ | grep -v "var(--color"
   ```
2. Replace any remaining hardcoded colors with CSS variable references.
3. Check for inline SVG fills or strokes that use hardcoded colors.
4. Check for `backgroundImage` gradients that may need dark variants.
5. Verify OpenUI components (`@openuidev/react-ui`) respect CSS variables. If not, add wrapper overrides.

**Commit:** `fix(web-ui): replace hardcoded colors with CSS variables for dark mode`

### §3 — Component-specific dark mode fixes

**Why:** Some components have custom visual elements that need explicit dark mode handling.

In `web-ui/src/components/workflow-editor/NodePropertiesPanel.css`:
```css
.node-properties__input {
  background: var(--color-bg);
  color: var(--color-text);
  border-color: var(--color-border);
}
.node-properties__input::placeholder {
  color: var(--color-text-muted);
}
```

In `web-ui/src/pages/Login.css`:
```css
.login-page {
  background: var(--color-surface);
}
.login-card {
  background: var(--color-surface-raised);
}
.login-code-digit {
  background: var(--color-bg);
  color: var(--color-text);
  border-color: var(--color-border);
}
```

In `web-ui/src/components/Modal.css`:
```css
.modal-overlay {
  background: rgba(0, 0, 0, 0.7);
}
.modal-content {
  background: var(--color-surface-raised);
}
```

In `web-ui/src/pages/Dashboard.css`:
```css
.stat-card {
  background: var(--color-surface-raised);
  border-color: var(--color-border);
}
```

In `web-ui/src/components/layout/StickyNav.css`:
```css
.nav-sidebar,
.nav-mobile-topbar,
.nav-mobile-overlay {
  background: var(--color-surface-raised);
  border-color: var(--color-border);
}
```

**Commit:** `fix(web-ui): component-specific dark mode styles`

### §4 — Code syntax highlighting in dark mode

**Why:** The workflow editor shows code snippets with inline syntax highlighting. The highlight colors may not be visible on dark backgrounds.

In `web-ui/src/components/workflow-editor/NodePropertiesPanel.css`:

```css
.syntax-highlight {
  background: var(--color-surface);
  border: var(--border-thin);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
  font-size: var(--font-size-sm);
  overflow-x: auto;
}

.syntax-keyword { color: var(--color-primary); }
.syntax-string { color: var(--color-success); }
.syntax-number { color: var(--color-warning); }
.syntax-comment { color: var(--color-text-muted); }
.syntax-variable { color: var(--color-text); }
```

**Commit:** `feat(web-ui): dark mode syntax highlighting`

### §5 — Toast notifications in dark mode

**Why:** Toast notifications may have hardcoded background colors.

In `web-ui/src/components/ToastContainer.css`:
```css
.toast {
  background: var(--color-surface-raised);
  color: var(--color-text);
  border: var(--border-thin);
  box-shadow: var(--shadow-lg);
}
.toast--success { border-left: 3px solid var(--color-success); }
.toast--error   { border-left: 3px solid var(--color-danger); }
.toast--warning { border-left: 3px solid var(--color-warning); }
.toast--info    { border-left: 3px solid var(--color-primary); }
```

**Commit:** `fix(web-ui): dark mode toast notifications`

### §6 — Empty state illustrations

**Why:** EmptyState component may use muted gray icons that are invisible on dark backgrounds.

In `web-ui/src/components/EmptyState.css`:
```css
.empty-state__icon {
  color: var(--color-text-muted);
  opacity: 0.5;
}
```

Ensure the icon SVG uses `currentColor` so it inherits the text color.

**Commit:** `fix(web-ui): dark mode empty state icons`

### §7 — System preference listener

**Why:** If the user selects "System", the theme should update when the OS theme changes.

In `web-ui/src/hooks/useTheme.ts`:

```typescript
useEffect(() => {
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const handler = () => {
    if (theme === 'system') {
      document.documentElement.setAttribute('data-theme', getSystemTheme());
    }
  };
  media.addEventListener('change', handler);
  return () => media.removeEventListener('change', handler);
}, [theme]);
```

**Commit:** `feat(web-ui): listen for OS theme changes`

### §8 — Tests

1. **Theme toggle test:** Click light/dark/system buttons. Assert `data-theme` attribute changes.
2. **Persistence test:** Set theme to dark. Reload page. Assert theme is still dark.
3. **System preference test:** Mock `matchMedia` to return `prefers-color-scheme: dark`. Assert effective theme is dark.
4. **Visual regression:** Screenshot key pages (Login, Dashboard, Profile, Workflow Editor) in both themes. Compare for no broken elements.

**Commit:** `test(web-ui): dark mode tests`

## Evaluation

- All pages are readable and usable in dark mode
- Theme toggle is visible and functional on all screen sizes
- Theme preference persists across sessions
- System preference is respected when selected
- No hardcoded colors remain that break in dark mode
- Syntax highlighting, toasts, modals, and empty states all adapt

## Acceptance

- `npm run build` in `web-ui/` passes
- `npx vitest run` green
- Manual visual check in both light and dark modes at 375px and 1440px
- `.kimi-done` includes `LOOP=L186`
