# L119 — Config Form Dropdowns for Enumerated Values

**Status:** Spec only
**Branch:** `feature/l119-config-dropdowns` (from `develop`)
**Depends on:** L111 (config editor page)

## Intent

The config editor currently renders every value as a text input (or checkbox for booleans, text for arrays). Fields with a fixed set of valid values — trust preset, model selection, platform state, temperature, and status fields — should use dropdowns (`<select>`) to prevent invalid input and improve UX.

## Scope

### §1 — Identify enumerated fields

In `src/hestia/config.py` and the config structure, the following fields have closed sets of valid values:

| Field | Valid values | Location in config |
|-------|-------------|-------------------|
| `trust.preset` | `paranoid`, `prompt_on_mobile`, `household`, `developer` | `trust.preset` |
| `inference.model_name` | Any `.gguf` filename (open set, but could show cached models) | `inference.model_name` |
| `platforms.telegram.allowed_users` | Array of strings (keep as text input) | `telegram.allowed_users` |

Additionally, runtime config fields that should be dropdowns:
- `inference.stt_model` / `inference.tts_voice` (if voice config is exposed)
- `storage.compression` (if exposed)

For this loop, focus on the high-impact closed enums:
- `trust.preset`
- Any boolean fields (already checkboxes — skip)

**Commit:** `docs: enumerate config fields that need dropdown rendering`

### §2 — Backend: expose valid values

Add a `GET /api/config/schema` endpoint in `src/hestia/web/routes/config.py` that returns metadata about config fields:

```json
{
  "schema": {
    "trust.preset": {
      "type": "enum",
      "values": ["paranoid", "prompt_on_mobile", "household", "developer"],
      "default": "developer"
    },
    "inference.model_name": {
      "type": "string",
      "suggestions": ["Qwen3.5-9B-UD-Q4_K_XL.gguf"]
    }
  }
}
```

Start with just the enum fields. The endpoint can be hardcoded or derived from dataclass metadata in the future. For now, a simple dict in the route module is sufficient.

**Commit:** `feat(web): add /api/config/schema endpoint for enum metadata`

### §3 — Frontend: render dropdowns

Update `web-ui/src/components/ConfigForm.tsx`:

- On mount (or when `initialConfig` changes), fetch `/api/config/schema`
- In `renderField`, before rendering a text input, check if the field path exists in the schema
- If `type === 'enum'`, render a `<select>` with `<option>` for each valid value
- The select should show the current value and call `updateValue` on change
- Style the select to match existing inputs (border, padding, border-radius)

```tsx
if (schema[fullPath]?.type === 'enum') {
  input = (
    <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
      <span>{key}</span>
      <select
        value={String(value)}
        onChange={(e) => updateValue(fullPath, e.target.value)}
        style={baseStyle}
      >
        {schema[fullPath].values.map((v: string) => (
          <option key={v} value={v}>{v}</option>
        ))}
      </select>
    </label>
  );
}
```

**Commit:** `feat(web-ui): render enum fields as dropdowns in config editor`

### §4 — Tests

1. Unit test `GET /api/config/schema` returns the expected enum metadata
2. Playwright test: config page renders a `<select>` for trust preset, changing it updates the form value
3. Verify no regression: non-enum fields still render as text inputs

**Commit:** `test(web): config schema endpoint and dropdown rendering`

## Evaluation

- **Spec check:** Schema endpoint, frontend dropdown rendering, focus on trust preset
- **Intent check:** User opens config editor, sees a dropdown for trust preset instead of a free-text input. Selecting "household" updates the value correctly.
- **Regression check:** Non-enum fields unchanged. All existing tests pass.

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` clean
- `ruff check src/ tests/` clean on changed files
- Trust preset renders as `<select>` with 4 options
- Other enum fields (if any added) render as dropdowns automatically
- `.kimi-done` includes `LOOP=L119`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
