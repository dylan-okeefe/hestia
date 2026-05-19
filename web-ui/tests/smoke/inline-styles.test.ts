import { execSync } from 'child_process';
import { describe, it, expect } from 'vitest';
import path from 'path';

describe('inline styles regression guard', () => {
  it('has fewer than 20 inline style={{...}} occurrences in src/', () => {
    const srcPath = path.resolve(__dirname, '../../src');
    const output = execSync(
      `grep -r "style={{" "${srcPath}" | grep -v "node_modules" | wc -l`,
      { encoding: 'utf-8' }
    );
    const count = parseInt(output.trim(), 10);
    expect(count).toBeLessThan(20);
  });
});
