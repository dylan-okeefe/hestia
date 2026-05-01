import { useState, useEffect, useRef } from 'react';
import { requestCode, verifyCode } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const { auth, login } = useAuth();
  const [phase, setPhase] = useState<'select' | 'input'>('select');
  const [selectedPlatform, setSelectedPlatform] = useState<string>('');
  const [code, setCode] = useState('');
  const [expiresIn, setExpiresIn] = useState(300);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const startTimer = (seconds: number) => {
    setExpiresIn(seconds);
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setExpiresIn((prev) => {
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  };

  const handleRequestCode = async (platform: string) => {
    setError(null);
    setSending(true);
    try {
      const data = await requestCode(platform);
      setSelectedPlatform(platform);
      setPhase('input');
      startTimer(data.expires_in || 300);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSending(false);
    }
  };

  const handleVerify = async () => {
    if (!code) return;
    setError(null);
    setVerifying(true);
    try {
      const data = await verifyCode(code);
      login(data.token);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setVerifying(false);
    }
  };

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        background: '#f5f5f5',
      }}
    >
      <div
        style={{
          background: '#fff',
          padding: '2rem',
          borderRadius: '8px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
          width: '100%',
          maxWidth: '360px',
        }}
      >
        <h1 style={{ margin: '0 0 0.5rem', fontSize: '1.5rem' }}>Hestia Dashboard</h1>
        <p style={{ margin: '0 0 1.5rem', color: '#666' }}>Authenticate via your chat platform</p>

        {phase === 'select' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {auth.availablePlatforms.length === 0 && (
              <p style={{ color: '#888' }}>No chat platforms are currently connected.</p>
            )}
            {auth.availablePlatforms.map((platform) => (
              <button
                key={platform}
                onClick={() => handleRequestCode(platform)}
                disabled={sending}
                style={{
                  padding: '0.75rem',
                  fontSize: '1rem',
                  cursor: 'pointer',
                  textTransform: 'capitalize',
                }}
              >
                {sending && selectedPlatform === platform
                  ? 'Sending…'
                  : `Send code via ${platform}`}
              </button>
            ))}
          </div>
        )}

        {phase === 'input' && (
          <div>
            <p style={{ margin: '0 0 0.5rem' }}>
              Enter the code sent to <strong>{selectedPlatform}</strong>
            </p>
            <input
              type="text"
              inputMode="numeric"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="000000"
              style={{
                width: '100%',
                padding: '0.75rem',
                fontSize: '1.25rem',
                letterSpacing: '0.5rem',
                textAlign: 'center',
                marginBottom: '0.5rem',
                borderRadius: '4px',
                border: '1px solid #ccc',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.85rem', color: expiresIn > 0 ? '#666' : '#f44336' }}>
                {expiresIn > 0 ? `Expires in ${formatTime(expiresIn)}` : 'Code expired'}
              </span>
              <button onClick={handleVerify} disabled={verifying || code.length < 6 || expiresIn <= 0}>
                {verifying ? 'Verifying…' : 'Verify'}
              </button>
            </div>
            <button
              onClick={() => {
                setPhase('select');
                setCode('');
                if (timerRef.current) clearInterval(timerRef.current);
              }}
              style={{
                marginTop: '0.75rem',
                background: 'none',
                border: 'none',
                color: '#1976d2',
                cursor: 'pointer',
                fontSize: '0.85rem',
              }}
            >
              ← Back to platform selection
            </button>
          </div>
        )}

        {error && (
          <p style={{ color: '#f44336', marginTop: '1rem', fontSize: '0.9rem' }}>{error}</p>
        )}
      </div>
    </div>
  );
}
