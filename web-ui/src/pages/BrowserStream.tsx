import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { startBrowserStream, stopBrowserStream, getAuthToken } from '../api/client';
import { useApiMutation } from '../hooks/useApi';
import { useToast } from '../hooks/useToast';
import PageCard from '../components/layout/PageCard';
import './BrowserStream.css';

const CANVAS_WIDTH = 960;
const CANVAS_HEIGHT = 540;
const SERVER_WIDTH = 1920;
const SERVER_HEIGHT = 1080;
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
  const [session, setSession] = useState<{ session_id: string; domain: string; ws_url: string } | null>(null);
  const [connected, setConnected] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [countdown, setCountdown] = useState(SESSION_TIMEOUT_MS);
  const [timedOut, setTimedOut] = useState(false);
  const [mobileText, setMobileText] = useState('');
  const [inputMode, setInputMode] = useState<'text' | 'password'>('text');

  const startMut = useApiMutation(startBrowserStream);
  const stopMut = useApiMutation(stopBrowserStream);

  const startTimeRef = useRef<number | null>(null);
  const autoStartedRef = useRef(false);
  const stoppingRef = useRef(false);

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
              ctx.drawImage(img, 0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
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
      const data = await startMut.mutateAsync(url.trim());
      setSession(data);
      setConnected(false);
      setTimedOut(false);
      startTimer();
      connectWebSocket(data.ws_url);
    } catch (err: any) {
      addToast({ message: err.message || 'Failed to start session', type: 'error', duration: 5000 });
    }
  };

  const handleDone = async () => {
    const domain = session?.domain;
    stoppingRef.current = true;
    try {
      await stopMut.mutateAsync(undefined as unknown as string);
      addToast({ message: 'Session saved', type: 'success', duration: 3000 });
    } catch (err: any) {
      addToast({ message: err.message || 'Failed to stop session', type: 'error', duration: 5000 });
    } finally {
      closeWs();
      clearTimer();
      navigate('/browser-sessions', { state: domain ? { checkedDomain: domain } : undefined });
    }
  };

  const handleCancel = async () => {
    stoppingRef.current = true;
    try {
      await stopMut.mutateAsync(undefined as unknown as string);
    } catch {
      // ignore
    } finally {
      closeWs();
      clearTimer();
      navigate('/browser-sessions');
    }
  };

  useEffect(() => {
    return () => {
      closeWs();
      clearTimer();
      if (session && !stoppingRef.current) {
        stoppingRef.current = true;
        stopBrowserStream().catch(() => {});
      }
    };
  }, [closeWs, clearTimer, session]);

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
    if (!session && url.trim() && !autoStartedRef.current && !startMut.isPending) {
      autoStartedRef.current = true;
      handleStart();
    }
  }, [session, url, startMut.isPending]);

  useEffect(() => {
    if (timedOut) {
      addToast({ message: 'Session timed out', type: 'warning', duration: 5000 });
      closeWs();
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
    const scaleX = SERVER_WIDTH / CANVAS_WIDTH;
    const scaleY = SERVER_HEIGHT / CANVAS_HEIGHT;
    const x = Math.round(((clientX - rect.left) / rect.width) * CANVAS_WIDTH * scaleX);
    const y = Math.round(((clientY - rect.top) / rect.height) * CANVAS_HEIGHT * scaleY);
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

      <canvas
        ref={canvasRef}
        width={CANVAS_WIDTH}
        height={CANVAS_HEIGHT}
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
