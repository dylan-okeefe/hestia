# L190 — Frontend Component Infrastructure

**Status:** Spec only  
**Branch:** `feature/l190-frontend-component-infrastructure` (from `develop`)  
**Depends on:** L184 (shared CSS system), L187 (post-review fixes)

## Intent

The review identified three structural gaps in the frontend: no shared Button component, no toast/notification system, and no field-level form validation display. This loop fills all three with consistent, reusable components.

## Scope

### §1 — Shared Button component

**Why:** Buttons use raw `<button>` with ad-hoc class combinations across the app. A `Button` with `variant` props reduces inconsistency.

**Create `web-ui/src/components/Button.tsx` + `Button.css`:**

```tsx
type ButtonVariant = 'primary' | 'danger' | 'ghost' | 'outline' | 'link';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: React.ReactNode;
}
```

- Map variants to CSS classes (`btn--primary`, `btn--danger`, etc.)
- Sizes adjust padding and font-size
- `loading` shows a spinner and disables the button
- `icon` renders before the label with proper spacing
- Forward refs and spread remaining props to the native `<button>`

**In `web-ui/src/styles/components.css`:**

- Add `.btn`, `.btn--primary`, `.btn--danger`, `.btn--ghost`, `.btn--outline`, `.btn--link`
- Use existing CSS variables for colors
- Add hover, active, disabled, and focus states
- Add size modifiers `.btn--sm`, `.btn--md`, `.btn--lg`

**Migrate 2-3 existing buttons as proof of concept** (e.g., in AdminUsers delete modal, ErrorDashboard resolve action). Full migration can happen incrementally in future loops.

**Commit:** `feat(web-ui): add reusable Button component with variants`

---

### §2 — Toast/notification system

**Why:** Actions like "save profile", "delete user", and "resolve error" have no visible success feedback. `ToastContainer.css` exists but no component uses it.

**Create `web-ui/src/components/ToastContainer.tsx`:**

- Renders a fixed-position container (top-right or bottom-right)
- Accepts a list of toasts: `{ id, message, type, duration }`
- Auto-dismisses after `duration` ms
- Types: `success`, `error`, `warning`, `info`
- Uses existing `ToastContainer.css` styles

**Create `web-ui/src/hooks/useToast.ts`:**

```typescript
const { toasts, addToast, removeToast } = useToast();
addToast({ message: 'User deleted', type: 'success', duration: 3000 });
```

- Provide a `ToastProvider` at the app root (wrap around routes in `App.tsx`)
- Expose `useToast()` context hook

**Wire into 2-3 actions as proof of concept:**
- AdminUsers: "User deleted" / "User updated"
- ErrorDashboard: "Error resolved" / "Error ignored"
- Profile: "Profile saved"

**Commit:** `feat(web-ui): add toast notification system`

---

### §3 — Field-level form validation display

**Why:** Forms disable the save button on invalid state but never show *why* a field is invalid. Server-side Pydantic errors aren't surfaced at the field level either.

**Create `web-ui/src/components/forms/FormField.tsx`:**

```tsx
interface FormFieldProps {
  label: string;
  error?: string;
  children: React.ReactNode;
  required?: boolean;
}
```

- Wraps a label + input + error message
- Shows red border on the child input when `error` is present
- Renders error text below the input
- Adds `*` to label when `required`

**Create `web-ui/src/components/forms/FormField.css`:**

- `.form-field__label`, `.form-field__input--error`, `.form-field__error`
- Use `--color-danger` for error styling

**Wire into AdminUsers create/edit form as proof of concept:**
- Validate `display_name` is non-empty
- Validate `platform` is selected in identity modal
- Display server-side validation errors (from Pydantic) at the field level

**Commit:** `feat(web-ui): add field-level form validation display`

## Quality gates

```bash
cd web-ui && npm run build
cd web-ui && npx vitest run
```

Both must pass.

## Handoff

- Verify Button renders correctly in all variants and sizes
- Verify toasts appear and auto-dismiss
- Verify form fields show error states and server validation messages
