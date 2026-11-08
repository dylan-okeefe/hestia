// Coordinate math for the browser stream.
//
// The server screencasts a fixed-size frame (1920x1080 CSS pixels of the
// remote browser viewport). The frontend displays that frame inside a canvas
// whose backing buffer may be a different size and whose CSS box may be
// scaled again by the layout. Both the frame renderer and the pointer
// handlers must use the SAME contain-fit mapping so that a click at a
// visible point dispatches to the same viewport coordinates that were drawn
// there.

export interface Size {
  width: number;
  height: number;
}

export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface ContainFit {
  scale: number;
  offsetX: number;
  offsetY: number;
  width: number;
  height: number;
}

export interface FramePoint {
  x: number;
  y: number;
}

/** Fit *frame* inside *container* preserving aspect ratio, centered. */
export function fitContain(container: Size, frame: Size): ContainFit {
  const scale = Math.min(container.width / frame.width, container.height / frame.height);
  const width = frame.width * scale;
  const height = frame.height * scale;
  return {
    scale,
    offsetX: (container.width - width) / 2,
    offsetY: (container.height - height) / 2,
    width,
    height,
  };
}

/**
 * Map a pointer position (clientX/clientY, CSS pixels relative to the
 * viewport) to coordinates in the streamed frame.
 *
 * - Handles the box being scaled by layout (width: 100% etc.) because it
 *   works from getBoundingClientRect(), which is already in CSS pixels.
 * - Handles letterboxing: offsets from fitContain are subtracted before
 *   scaling, so clicks in the black bars return null.
 * - Handles page scroll: clientX/clientY and getBoundingClientRect() are
 *   both viewport-relative, so scroll cancels out.
 * - devicePixelRatio needs no handling: neither input is in device pixels.
 *
 * Returns null when the pointer is outside the frame image.
 */
export function pointerToFrameCoords(
  clientX: number,
  clientY: number,
  rect: Rect,
  frame: Size,
): FramePoint | null {
  if (rect.width <= 0 || rect.height <= 0 || frame.width <= 0 || frame.height <= 0) {
    return null;
  }
  const fit = fitContain({ width: rect.width, height: rect.height }, frame);
  const relX = clientX - rect.left - fit.offsetX;
  const relY = clientY - rect.top - fit.offsetY;
  if (relX < 0 || relY < 0 || relX > fit.width || relY > fit.height) {
    return null;
  }
  return {
    x: Math.round(relX / fit.scale),
    y: Math.round(relY / fit.scale),
  };
}
