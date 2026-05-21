import { createTheme } from '@openuidev/react-ui';

export const hestiaTheme = createTheme({
  // Primary: indigo/slate blue
  interactiveAccentDefault: '#2563eb',
  interactiveAccentHover: '#1d4ed8',
  interactiveAccentPressed: '#1e40af',
  interactiveAccentDisabled: 'rgba(37, 99, 235, 0.4)',

  // Danger: red for destructive actions
  interactiveDestructiveAccentDefault: '#dc2626',
  interactiveDestructiveAccentHover: '#b91c1c',
  interactiveDestructiveAccentPressed: '#991b1b',
  interactiveDestructiveAccentDisabled: 'rgba(220, 38, 38, 0.4)',

  // Surface: neutral grays
  background: '#f8fafc',
  foreground: '#f1f5f9',
  popoverBackground: '#ffffff',

  // Font stack: system-ui, sans-serif
  fontBody: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  fontHeading: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  fontLabel: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  fontNumbers: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
});
