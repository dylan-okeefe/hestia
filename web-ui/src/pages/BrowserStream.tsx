import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { startBrowserStream, stopBrowserStream, restartHeadedBrowserStream, getAuthToken } from '../api/client';
import { useApiMutation } from '../hooks/useApi';
import { useToast } from '../hooks/useToast';
import PageCard from '../components/layout/PageCard';
import './BrowserStream.css';

const DEFAULT_WIDTH = 960;
const DEFAULT_HEIGHT = 540;
const SERVER_WIDTH = 1920;
const SERVER_HEIGHT = 1080;
const MIN_WIDTH = 320;
const MIN_HEIGHT = 180;
const MAX_WIDTH = 1920;
const MAX_HEIGHT = 1080;
const SESSION_TIMEOUT_MS = 10 * 60 * 1000;

function formatMs(mmss: number): string {
  const totalSeconds = Math.floor(mmss / 1000);
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function buildWsUrl(relativeUrl: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}${relativeUrl}`;
}

export default function BrowserStream() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { addToast } = useToast();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [url, setUrl] = useState(searchParams.get('url') || '');
  const [headed, setHeaded] = useState(searchParams.get('headed') === 'true');
  const [session, setSession] = useState<{ session_id: string; domain: string; ws_url: string } | null>(null);
  const [connected, setConnected] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [countdown, setCountdown] = useState(SESSION_TIMEOUT_MS);
  const [timedOut, setTimedOut] = useState(false);
  const [mobileText, setMobileText] = useState('');
  const [inputMode, setInputMode] = useState<'text' | 'password'>('text');
  const [currentUrl, setCurrentUrl] = useState('');
  const [canvasSize, setCanvasSize] = useState({ width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT });

  const startMut = useApiMutation(startBrowserStream);
  const stopMut = useApiMutation(stopBrowserStream);
  const restartHeadedMut = useApiMutation(restartHeadedBrowserStream);

  const startTimeRef = useRef<number | null>(null);
  const autoStartedRef = useRef(false);
  const shouldAutoStartRef = useRef(!!searchParams.get('url'));
  const stoppingRef = useRef(false);
  const sessionRef = useRef(session);
  sessionRef.current = session;

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const closeWs = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const startTimer = useCallback(() => {
    clearTimer();
    startTimeRef.current = Date.now();
    timerRef.current = setInterval(() => {
      const now = Date.now();
      const start = startTimeRef.current ?? now;
      const el = now - start;
      const remaining = SESSION_TIMEOUT_MS - el;
      setElapsed(el);
      setCountdown(remaining);
      if (remaining <= 0) {
        setTimedOut(true);
        clearTimer();
      }
    }, 1000);
  }, [clearTimer]);

  const connectWebSocket = useCallback((wsUrl: string) => {
    closeWs();
    const token = getAuthToken();
    const fullUrl = token ? `${buildWsUrl(wsUrl)}?token=${encodeURIComponent(token)}` : buildWsUrl(wsUrl);
    const ws = new WebSocket(fullUrl);
    ws.binaryType = 'blob';

    ws.onopen = () => {
      console.log('[ws] open');
      setConnected(true);
    };
    ws.onclose = (e) => {
      console.log('[ws] close', e.code, e.reason);
      setConnected(false);
    };
    ws.onerror = (err) => console.error('[ws] error', err);
    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'input_mode' && (msg.mode === 'text' || msg.mode === 'password')) {
            setInputMode(msg.mode);
          }
        } catch {
          // ignore non-JSON text messages
        }
        return;
      }
      if (event.data instanceof Blob) {
        const blobUrl = URL.createObjectURL(event.data);
        const img = new Image();
        img.onload = () => {
          const canvas = canvasRef.current;
          if (canvas) {
            const ctx = canvas.getContext('2d');
            if (ctx) {
              ctx.drawImage(img, 0, 0, canvasSize.width, canvasSize.height);
            }
          }
          URL.revokeObjectURL(blobUrl);
        };
        img.onerror = () => {
          URL.revokeObjectURL(blobUrl);
        };
        img.src = blobUrl;
      }
    };

    wsRef.current = ws;
  }, [closeWs]);

  const handleStart = async () => {
    if (!url.trim()) return;
    try {
      const data = await startMut.mutateAsync({ url: url.trim(), headed });
      setSession(data);
      setCurrentUrl(data.url || url.trim());
      setConnected(false);
      setTimedOut(false);
      startTimer();
      connectWebSocket(data.ws_url);
    } catch (err: any) {
      addToast({ message: err.message || 'Failed to start session', type: 'error', duration: 5000 });
    }
  };

  const handleDone = async () => {
    stoppingRef.current = true;
    try {
      await stopMut.mutateAsync();
      addToast({ message: 'Session saved', type: 'success', duration: 3000 });
    } catch (err: any) {
      addToast({ message: err.message || 'Failed to stop session', type: 'error', duration: 5000 });
    } finally {
      closeWs();
      clearTimer();
      navigate('/browser-sessions');
    }
  };

  const handleCancel = async () => {
    stoppingRef.current = true;
    try {
      await stopMut.mutateAsync();
    } catch {
      // ignore
    } finally {
      closeWs();
      clearTimer();
      navigate('/browser-sessions');
    }
  };

  const handleRestartHeaded = async () => {
    try {
      await restartHeadedMut.mutateAsync();
      setHeaded(true);
      addToast({ message: 'Switched to headed browser', type: 'success', duration: 3000 });
    } catch (err: any) {
      addToast({ message: err.message || 'Failed to switch to headed browser', type: 'error', duration: 5000 });
    }
  };

  useEffect(() => {
    return () => {
      closeWs();
      clearTimer();
      if (sessionRef.current && !stoppingRef.current) {
        stoppingRef.current = true;
        stopBrowserStream().catch(() => {});
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    autoStartedRef.current = false;
  }, []);

  useEffect(() => {
    const onPageShow = (e: PageTransitionEvent) => {
      if (e.persisted) {
        autoStartedRef.current = false;
      }
    };
    window.addEventListener('pageshow', onPageShow);
    return () => window.removeEventListener('pageshow', onPageShow);
  }, []);

  useEffect(() => {
    if (!session && url.trim() && !autoStartedRef.current && !startMut.isPending && shouldAutoStartRef.current) {
      autoStartedRef.current = true;
      shouldAutoStartRef.current = false;
      handleStart();
    }
  }, [session, url, startMut.isPending]);

  useEffect(() => {
    if (timedOut) {
      addToast({ message: 'Session timed out', type: 'warning', duration: 5000 });
      closeWs();
      stopBrowserStream().catch(() => {});
      navigate('/browser-sessions');
    }
  }, [timedOut, closeWs, navigate, addToast]);

  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (session) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [session]);

  const sendWsMessage = useCallback((msg: object) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const getScaledCoords = (clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const scaleX = SERVER_WIDTH / canvasSize.width;
    const scaleY = SERVER_HEIGHT / canvasSize.height;
    const x = Math.round(((clientX - rect.left) / rect.width) * canvasSize.width * scaleX);
    const y = Math.round(((clientY - rect.top) / rect.height) * canvasSize.height * scaleY);
    return { x, y };
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = getScaledCoords(e.clientX, e.clientY);
    sendWsMessage({ type: 'click', x, y });
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = getScaledCoords(e.clientX, e.clientY);
    sendWsMessage({ type: 'mousemove', x, y });
  };

  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const { x, y } = getScaledCoords(e.clientX, e.clientY);
    sendWsMessage({ type: 'scroll', x, y, deltaX: e.deltaX, deltaY: e.deltaY });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLCanvasElement>) => {
    const specialKeys = ['Tab', 'Enter', 'Backspace', 'Escape', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'];
    if (specialKeys.includes(e.key)) {
      e.preventDefault();
      sendWsMessage({ type: 'keydown', key: e.key });
    } else if (e.key.length === 1) {
      sendWsMessage({ type: 'type', text: e.key });
    }
  };

  const handleMobileSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (mobileText.trim()) {
      sendWsMessage({ type: 'type', text: mobileText });
      setMobileText('');
    }
  };

  const handleNavigate = (e: React.FormEvent) => {
    e.preventDefault();
    if (currentUrl.trim()) {
      sendWsMessage({ type: 'navigate', url: currentUrl.trim() });
    }
  };

  const handleWidthChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const width = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, parseInt(e.target.value, 10) || DEFAULT_WIDTH));
    setCanvasSize((prev) => ({ ...prev, width }));
  };

  const handleHeightChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const height = Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, parseInt(e.target.value, 10) || DEFAULT_HEIGHT));
    setCanvasSize((prev) => ({ ...prev, height }));
  };

  if (!session) {
    return (
      <div className="browser-stream-page">
        <h1 className="browser-stream-title">New Browser Session</h1>
        <PageCard className="browser-stream-start-card">
          <div className="stack-md">
            <label className="form-label" htmlFor="stream-url">URL</label>
            <input
              id="stream-url"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/login"
              className="form-input"
              disabled={startMut.isPending}
            />
            <label className="form-row">
              <input
                type="checkbox"
                checked={headed}
                onChange={(e) => setHeaded(e.target.checked)}
                disabled={startMut.isPending}
              />
              <span className="text-small">Headed browser (use real browser window for bot-blocking sites)</span>
            </label>
            <button onClick={handleStart} disabled={startMut.isPending || !url.trim()}>
              {startMut.isPending ? 'Starting…' : 'Start Session'}
            </button>
            {startMut.error && <p className="text-danger text-small">{startMut.error.message}</p>}
          </div>
        </PageCard>
      </div>
    );
  }

  return (
    <div className="browser-stream-page">
      <div className="browser-stream-status-bar">
        <span className="browser-stream-domain">{session.domain}</span>
        <span className="browser-stream-timer">Elapsed: {formatMs(elapsed)}</span>
        <span className={`browser-stream-timer ${countdown < 60000 ? 'browser-stream-timer--warning' : ''}`}>
          Remaining: {formatMs(Math.max(0, countdown))}
        </span>
        <span className="browser-stream-connection">
          <span className={`status-dot-sm ${connected ? 'status-dot-sm--success' : 'status-dot-sm--danger'}`} />
          {connected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      <form onSubmit={handleNavigate} className="browser-stream-url-bar">
        <label className="form-label" htmlFor="stream-current-url">URL</label>
        <input
          id="stream-current-url"
          type="url"
          value={currentUrl}
          onChange={(e) => setCurrentUrl(e.target.value)}
          placeholder="https://example.com/login"
          className="form-input"
        />
        <button type="submit" disabled={!currentUrl.trim()}>
          Go
        </button>
      </form>

      <div className="browser-stream-size-bar">
        <label className="form-label" htmlFor="stream-width">Width</label>
        <input
          id="stream-width"
          type="number"
          min={MIN_WIDTH}
          max={MAX_WIDTH}
          value={canvasSize.width}
          onChange={handleWidthChange}
          className="form-input form-input--number"
        />
        <label className="form-label" htmlFor="stream-height">Height</label>
        <input
          id="stream-height"
          type="number"
          min={MIN_HEIGHT}
          max={MAX_HEIGHT}
          value={canvasSize.height}
          onChange={handleHeightChange}
          className="form-input form-input--number"
        />
      </div>

      <canvas
        ref={canvasRef}
        width={canvasSize.width}
        height={canvasSize.height}
        className="browser-stream-canvas"
        tabIndex={0}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onWheel={handleWheel}
        onKeyDown={handleKeyDown}
      />

      <form onSubmit={handleMobileSubmit} className="browser-stream-mobile-input">
        <label className="form-label" htmlFor="mobile-text">Type text</label>
        <div className="row-md">
          <input
            id="mobile-text"
            type={inputMode}
            value={mobileText}
            onChange={(e) => setMobileText(e.target.value)}
            placeholder={inputMode === 'password' ? 'Password…' : 'Type here and press Enter…'}
            className="form-input"
          />
          <button type="submit" disabled={!mobileText.trim()}>
            Send
          </button>
        </div>
      </form>

      <div className="browser-stream-controls">
        {!headed && (
          <button
            onClick={handleRestartHeaded}
            disabled={restartHeadedMut.isPending || stopMut.isPending}
            title="Relaunch this stream as a visible browser window"
          >
            {restartHeadedMut.isPending ? 'Switching…' : 'Use Headed'}
          </button>
        )}
        <button onClick={handleDone} disabled={stopMut.isPending}>
          {stopMut.isPending ? 'Stopping…' : 'Done'}
        </button>
        <button onClick={handleCancel} className="text-danger border-danger" disabled={stopMut.isPending}>
          Cancel
        </button>
      </div>

    </div>
  );
}
