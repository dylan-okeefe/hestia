import { test, expect } from '@playwright/test';
import { mockApis } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApis(page);
  await page.route('/api/auth/status', (route) => route.fulfill({
    json: { auth_enabled: true, authenticated: true, user_id: 'browser-test-admin' },
  }));
  await page.route('/api/users/browser-test-admin', (route) => route.fulfill({
    json: { id: 'browser-test-admin', display_name: 'Browser test admin', role: 'admin', identities: [] },
  }));
});

test('browser stream start mode is visible', async ({ page }) => {
  await page.goto('/browser-sessions/stream');
  await expect(page.locator('h1')).toHaveText('New Browser Session');
  await expect(page.locator('input#stream-url')).toBeVisible();
  await expect(page.locator('button:has-text("Start Session")')).toBeVisible();
});

test('browser stream can start and show canvas', async ({ page }) => {
  await page.goto('/browser-sessions/stream');
  await page.fill('input#stream-url', 'https://example.com/login');

  // Mock the WebSocket connection so the page can connect
  await page.route('/api/browser-session/stream/test-session-001**', async (route) => {
    await route.fulfill({ status: 200 });
  });

  await page.click('button:has-text("Start Session")');

  // Canvas should become visible after start
  await expect(page.locator('canvas.browser-stream-canvas')).toBeVisible();

  // Status bar should show domain and timer
  await expect(page.locator('.browser-stream-domain')).toHaveText('example.com');
  await expect(page.locator('.browser-stream-timer').first()).toContainText('Elapsed:');
});

test('cancel button navigates back to browser sessions list', async ({ page }) => {
  await page.goto('/browser-sessions/stream');
  await page.fill('input#stream-url', 'https://example.com/login');

  await page.route('/api/browser-session/stream/test-session-001**', async (route) => {
    await route.fulfill({ status: 200 });
  });

  await page.click('button:has-text("Start Session")');
  await expect(page.locator('canvas.browser-stream-canvas')).toBeVisible();

  await page.click('button:has-text("Cancel")');
  await expect(page).toHaveURL(/\/browser-sessions$/);
});

test.describe('resized stream input', () => {
  test.use({ deviceScaleFactor: 2, viewport: { width: 920, height: 1000 } });

  test('ignores letterbox clicks and maps visible clicks and scrolling to the frame', async ({ page }) => {
    const pointerEvents: Array<{ type: string; x: number; y: number; deltaY?: number }> = [];
    let sendFrame: ((frame: Buffer) => void) | undefined;
    await page.routeWebSocket('**/api/browser-session/stream/test-session-001**', (socket) => {
      sendFrame = (frame) => socket.send(frame);
      socket.onMessage((message) => {
        const event = JSON.parse(message.toString());
        if (event.type === 'click' || event.type === 'scroll') pointerEvents.push(event);
      });
    });

    await page.goto('/browser-sessions/stream');
    await page.locator('#stream-url').fill('https://example.com/login');
    await page.getByRole('button', { name: 'Start Session' }).click();

    const canvas = page.locator('canvas.browser-stream-canvas');
    await expect(canvas).toBeVisible();
    await page.locator('#stream-width').fill('640');
    await page.locator('#stream-height').fill('640');
    await expect(canvas).toHaveAttribute('height', '640');
    await expect(page.locator('.browser-stream-connection')).toHaveText('Connected');
    const encodedFrame = await page.evaluate(() => {
      const frame = document.createElement('canvas');
      frame.width = 16;
      frame.height = 9;
      const context = frame.getContext('2d')!;
      context.fillStyle = 'red';
      context.fillRect(0, 0, frame.width, frame.height);
      return frame.toDataURL('image/jpeg').split(',')[1];
    });
    if (!sendFrame) throw new Error('The mock stream did not connect');
    sendFrame(Buffer.from(encodedFrame, 'base64'));
    await expect.poll(() => canvas.evaluate((element: HTMLCanvasElement) => {
      const context = element.getContext('2d')!;
      return {
        center: context.getImageData(320, 320, 1, 1).data[0] > 200,
        letterbox: [...context.getImageData(320, 10, 1, 1).data],
      };
    })).toEqual({ center: true, letterbox: [0, 0, 0, 255] });
    await canvas.scrollIntoViewIfNeeded();
    const box = await canvas.boundingBox();
    if (!box) throw new Error('Stream canvas has no visible bounds');

    const x = box.x + box.width / 4;
    await page.mouse.click(x, box.y + box.height * 0.05);
    const y = box.y + box.height * 0.640625;
    await page.mouse.click(x, y);
    await page.mouse.wheel(0, 100);

    await expect.poll(() => pointerEvents.map((event) => event.type)).toEqual(['click', 'scroll']);
    for (const event of pointerEvents) {
      expect(Math.abs(event.x - 480)).toBeLessThanOrEqual(2);
      expect(Math.abs(event.y - 810)).toBeLessThanOrEqual(2);
    }
    expect(pointerEvents[1].deltaY).toBeGreaterThan(0);
  });
});
