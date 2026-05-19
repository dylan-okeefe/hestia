import { describe, it, expect } from 'vitest';
import { TEXT } from './text';

describe('TEXT catalog', () => {
  it('has no empty leaf values', () => {
    const walk = (obj: unknown, path: string) => {
      if (typeof obj === 'string') {
        expect(obj.length, `Empty string at ${path}`).toBeGreaterThan(0);
        return;
      }
      if (typeof obj === 'function') {
        const result = (obj as (...args: unknown[]) => string)(
          '',
          0,
          0,
          '',
          '',
          0,
          '',
          '',
          '',
          ''
        );
        expect(typeof result, `Non-string return at ${path}`).toBe('string');
        expect(result.length, `Empty return at ${path}`).toBeGreaterThan(0);
        return;
      }
      if (obj && typeof obj === 'object') {
        for (const [key, value] of Object.entries(obj)) {
          walk(value, path ? `${path}.${key}` : key);
        }
        return;
      }
      expect.fail(`Unexpected leaf type at ${path}: ${typeof obj}`);
    };
    walk(TEXT, 'TEXT');
  });

  it('has no duplicate strings with different casing', () => {
    const values: string[] = [];
    const walk = (obj: unknown) => {
      if (typeof obj === 'string') {
        values.push(obj);
        return;
      }
      if (typeof obj === 'function') {
        const result = (obj as (...args: unknown[]) => string)(
          '',
          0,
          0,
          '',
          '',
          0,
          '',
          '',
          '',
          ''
        );
        values.push(result);
        return;
      }
      if (obj && typeof obj === 'object') {
        for (const value of Object.values(obj)) {
          walk(value);
        }
      }
    };
    walk(TEXT);

    const seen = new Map<string, string>();
    for (const v of values) {
      const lower = v.toLowerCase();
      if (seen.has(lower)) {
        const first = seen.get(lower)!;
        expect(
          v,
          `Duplicate casing: "${first}" and "${v}"`
        ).toBe(first);
      } else {
        seen.set(lower, v);
      }
    }
  });
});
