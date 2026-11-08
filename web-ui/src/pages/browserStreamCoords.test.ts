import { describe, it, expect } from 'vitest';
import { fitContain, pointerToFrameCoords } from './browserStreamCoords';

const FRAME = { width: 1920, height: 1080 };

describe('fitContain', () => {
  it('scales uniformly when the container matches the frame aspect', () => {
    const fit = fitContain({ width: 960, height: 540 }, FRAME);
    expect(fit.scale).toBe(0.5);
    expect(fit.offsetX).toBe(0);
    expect(fit.offsetY).toBe(0);
    expect(fit.width).toBe(960);
    expect(fit.height).toBe(540);
  });

  it('letterboxes (vertical bars) when the container is wider than the frame aspect', () => {
    const fit = fitContain({ width: 1000, height: 500 }, FRAME);
    // Limited by height: scale = 500/1080
    expect(fit.scale).toBeCloseTo(500 / 1080);
    expect(fit.height).toBeCloseTo(500);
    expect(fit.offsetY).toBeCloseTo(0);
    expect(fit.width).toBeCloseTo(1920 * (500 / 1080));
    expect(fit.offsetX).toBeCloseTo((1000 - fit.width) / 2);
  });

  it('pillarboxes (horizontal bars) when the container is taller than the frame aspect', () => {
    const fit = fitContain({ width: 960, height: 700 }, FRAME);
    // Limited by width: scale = 960/1920 = 0.5
    expect(fit.scale).toBe(0.5);
    expect(fit.width).toBe(960);
    expect(fit.offsetX).toBe(0);
    expect(fit.height).toBe(540);
    expect(fit.offsetY).toBeCloseTo((700 - 540) / 2);
  });
});

describe('pointerToFrameCoords', () => {
  it('maps full-box clicks when the box matches the frame aspect (scale !== 1)', () => {
    // CSS box 960x540 displaying a 1920x1080 frame: scale 0.5, no offsets.
    const rect = { left: 0, top: 0, width: 960, height: 540 };
    expect(pointerToFrameCoords(480, 270, rect, FRAME)).toEqual({ x: 960, y: 540 });
    expect(pointerToFrameCoords(0, 0, rect, FRAME)).toEqual({ x: 0, y: 0 });
    expect(pointerToFrameCoords(960, 540, rect, FRAME)).toEqual({ x: 1920, y: 1080 });
  });

  it('subtracts letterbox offsets before scaling', () => {
    // 1000x500 box: frame rendered 888.9x500 starting at x=55.6.
    const rect = { left: 0, top: 0, width: 1000, height: 500 };
    const fit = fitContain({ width: 1000, height: 500 }, FRAME);
    // Center of the visible frame image.
    const cx = fit.offsetX + fit.width / 2;
    const cy = fit.offsetY + fit.height / 2;
    expect(pointerToFrameCoords(cx, cy, rect, FRAME)).toEqual({ x: 960, y: 540 });
    // A click in the left black bar is outside the frame.
    expect(pointerToFrameCoords(fit.offsetX / 2, cy, rect, FRAME)).toBeNull();
  });

  it('is independent of devicePixelRatio (inputs are CSS pixels)', () => {
    // Simulating a hi-DPI display: the rect is still reported in CSS pixels,
    // so the mapping must not change with devicePixelRatio.
    const dpr = 2;
    const rect = { left: 0, top: 0, width: 800 * dpr / dpr, height: 450 };
    expect(pointerToFrameCoords(400, 225, rect, FRAME)).toEqual({ x: 960, y: 540 });
  });

  it('handles page scroll via viewport-relative coordinates', () => {
    // After scrolling down 300px, getBoundingClientRect().top shifts by -300
    // and clientY is also measured from the viewport top, so the mapping is
    // unchanged.
    const rect = { left: 40, top: -300, width: 960, height: 540 };
    // Pointer at viewport (520, 10) is 480,310 into the box.
    expect(pointerToFrameCoords(520, 10, rect, FRAME)).toEqual({ x: 960, y: 620 });
  });

  it('accounts for a non-zero rect origin', () => {
    const rect = { left: 100, top: 50, width: 960, height: 540 };
    expect(pointerToFrameCoords(100, 50, rect, FRAME)).toEqual({ x: 0, y: 0 });
    expect(pointerToFrameCoords(1060, 590, rect, FRAME)).toEqual({ x: 1920, y: 1080 });
  });

  it('returns null outside the frame image', () => {
    const rect = { left: 0, top: 0, width: 960, height: 540 };
    expect(pointerToFrameCoords(-1, 270, rect, FRAME)).toBeNull();
    expect(pointerToFrameCoords(961, 270, rect, FRAME)).toBeNull();
    expect(pointerToFrameCoords(480, -1, rect, FRAME)).toBeNull();
    expect(pointerToFrameCoords(480, 541, rect, FRAME)).toBeNull();
  });

  it('returns null for degenerate rects', () => {
    expect(pointerToFrameCoords(0, 0, { left: 0, top: 0, width: 0, height: 540 }, FRAME)).toBeNull();
    expect(pointerToFrameCoords(0, 0, { left: 0, top: 0, width: 960, height: 0 }, FRAME)).toBeNull();
  });
});
