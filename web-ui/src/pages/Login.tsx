import { useState, useEffect, useRef } from 'react';
import { fetchAvailableUsers, requestCode, verifyCode } from '../api/client';
import { useAuth } from '../context/AuthContext';
import PageCard from '../components/layout/PageCard';
import EmptyState from '../components/layout/EmptyState';
import { label, ROLE_LABELS } from '../lib/labels';

interface AvailableIdentity {
  platform: string;
  platform_user: string;
}

interface AvailableUser {
  user_id: string;
  display_name: string;
  role: string;
  platforms: string[];
  identities: AvailableIdentity[];
}

const roleBadgeColor = (role: string) => {
  switch (role) {
    case 'admin':
      return '#2563eb';
    case 'trusted':
      return '#d97706';
    default:
      return '#6b7280';
  }
};

const platformHelperText: Record<string, string> = {
  matrix: 'A verification code will be sent to your Matrix DM.',
  telegram: 'A verification code will be sent via Telegram.',
  discord: 'A verification code will be sent via Discord DM.',
  email: 'A verification code will be sent to your email address.',
  cli: 'Check your terminal for the verification code.',
};

export default function Login() {
  const { login } = useAuth();
  const [phase, setPhase] = useState<'select-user' | 'select-platform' | 'input'>('select-user');
  const [availableUsers, setAvailableUsers] = useState<AvailableUser[]>([]);
  const [selectedUser, setSelectedUser] = useState<AvailableUser | null>(null);
  const [selectedPlatform, setSelectedPlatform] = useState<string>('');
  const [code, setCode] = useState('');
  const [expiresIn, setExpiresIn] = useState(300);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchAvailableUsers()
      .then((data) => {
        if (!cancelled) {
          const filtered = (data.users || []).filter(
            (u) => !u.display_name.startsWith('!')
          );
          setAvailableUsers(filtered);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAvailableUsers([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingUsers(false);
        }
      });
    return () => {
      cancelled = true;
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

  const handleSelectUser = (user: AvailableUser) => {
    setSelectedUser(user);
    setPhase('select-platform');
  };

  const handleRequestCode = async (platform: string) => {
    setError(null);
    setSending(true);
    try {
      let platformUser: string | undefined;
      if (selectedUser) {
        const identity = selectedUser.identities.find((i) => i.platform === platform);
        platformUser = identity?.platform_user;
      }
      const data = await requestCode(platform, platformUser);
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

  const steps = ['Select User', 'Select Platform', 'Enter Code'];
  const currentStepIndex = phase === 'select-user' ? 0 : phase === 'select-platform' ? 1 : 2;

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
      <div style={{ width: '100%', maxWidth: '480px', padding: '1rem' }}>
        <PageCard style={{ padding: '2rem' }}>
          <h1 style={{ margin: '0 0 0.5rem', fontSize: '1.5rem' }}>Hestia Dashboard</h1>
          <p style={{ margin: '0 0 1.5rem', color: '#666' }}>Authenticate via your chat platform</p>

          {/* Progress indicator */}
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
            {steps.map((step, index) => (
              <div
                key={step}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '0.25rem',
                  flex: 1,
                }}
              >
                <div
                  style={{
                    width: '28px',
                    height: '28px',
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '0.875rem',
                    fontWeight: 'bold',
                    background: index <= currentStepIndex ? '#2563eb' : '#e5e7eb',
                    color: index <= currentStepIndex ? '#fff' : '#6b7280',
                  }}
                >
                  {index + 1}
                </div>
                <span
                  style={{
                    fontSize: '0.7rem',
                    color: index <= currentStepIndex ? '#2563eb' : '#9ca3af',
                    fontWeight: index === currentStepIndex ? 'bold' : 'normal',
                  }}
                >
                  {step}
                </span>
              </div>
            ))}
          </div>

          {phase === 'select-user' && (
            <div>
              <p style={{ margin: '0 0 0.75rem', fontSize: '0.875rem', color: '#666' }}>
                Choose your user account to continue.
              </p>
              {loadingUsers && <EmptyState title="Loading users…" description="Please wait." />}
              {!loadingUsers && availableUsers.length === 0 && (
                <EmptyState
                  title="No users available"
                  description="No users configured. Contact your admin."
                />
              )}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '0.75rem' }}>
                {!loadingUsers && availableUsers.map((user) => (
                  <button
                    key={user.user_id}
                    onClick={() => handleSelectUser(user)}
                    style={{
                      padding: '1rem',
                      fontSize: '1rem',
                      cursor: 'pointer',
                      textAlign: 'center',
                      borderRadius: '8px',
                      border: '1px solid #eee',
                      background: '#fff',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      gap: '0.5rem',
                    }}
                  >
                    <span style={{ fontWeight: 'bold' }}>{user.display_name}</span>
                    <span
                      style={{
                        display: 'inline-block',
                        padding: '0.125rem 0.5rem',
                        borderRadius: '999px',
                        fontSize: '0.65rem',
                        fontWeight: 'bold',
                        color: '#fff',
                        background: roleBadgeColor(user.role),
                        textTransform: 'uppercase',
                      }}
                    >
                      {label(ROLE_LABELS, user.role)}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {phase === 'select-platform' && selectedUser && (
            <div>
              <p style={{ margin: '0 0 0.75rem', fontSize: '0.875rem', color: '#666' }}>
                Selected user: <strong>{selectedUser.display_name}</strong>
              </p>
              {selectedUser.platforms.length === 0 && (
                <EmptyState
                  title="No platforms available"
                  description="No platforms configured for this user."
                />
              )}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {selectedUser.platforms.map((platform) => (
                  <button
                    key={platform}
                    onClick={() => handleRequestCode(platform)}
                    disabled={sending}
                    style={{
                      padding: '0.75rem',
                      fontSize: '1rem',
                      cursor: 'pointer',
                      textTransform: 'capitalize',
                      textAlign: 'left',
                      borderRadius: '6px',
                      border: '1px solid #eee',
                      background: '#fff',
                    }}
                  >
                    <div style={{ fontWeight: 'bold', marginBottom: '0.25rem' }}>
                      {sending && selectedPlatform === platform
                        ? 'Sending…'
                        : `Send code via ${platform}`}
                    </div>
                    <div style={{ fontSize: '0.8rem', color: '#666' }}>
                      {platformHelperText[platform] || 'A verification code will be sent to your device.'}
                    </div>
                  </button>
                ))}
              </div>
              <button
                onClick={() => {
                  setPhase('select-user');
                  setSelectedUser(null);
                }}
                style={{
                  marginTop: '1rem',
                  background: 'none',
                  border: 'none',
                  color: '#1976d2',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                }}
              >
                ← Back to user selection
              </button>
            </div>
          )}

          {phase === 'input' && (
            <div>
              <p style={{ margin: '0 0 0.5rem', fontSize: '0.875rem', color: '#666' }}>
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
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                <span style={{ fontSize: '0.85rem', color: expiresIn > 0 ? '#666' : '#f44336' }}>
                  {expiresIn > 0 ? `Expires in ${formatTime(expiresIn)}` : 'Code expired'}
                </span>
                <button onClick={handleVerify} disabled={verifying || code.length < 6 || expiresIn <= 0}>
                  {verifying ? 'Verifying…' : 'Verify'}
                </button>
              </div>
              <button
                onClick={() => {
                  setPhase('select-platform');
                  setCode('');
                  if (timerRef.current) clearInterval(timerRef.current);
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#1976d2',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                }}
              >
                ← Back to platform selection
              </button>
              {expiresIn <= 0 && (
                <p style={{ margin: '0.5rem 0 0', fontSize: '0.8rem', color: '#666' }}>
                  Code expired.{' '}
                  <button
                    onClick={() => {
                      setPhase('select-platform');
                      setCode('');
                      if (timerRef.current) clearInterval(timerRef.current);
                    }}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#1976d2',
                      cursor: 'pointer',
                      fontSize: '0.8rem',
                      padding: 0,
                      textDecoration: 'underline',
                    }}
                  >
                    Resend code
                  </button>
                </p>
              )}
            </div>
          )}

          {error && (
            <PageCard style={{ marginTop: '1rem', marginBottom: 0, borderColor: '#fecaca', background: '#fef2f2' }}>
              <p style={{ color: '#ef4444', margin: 0, fontSize: '0.875rem' }}>{error}</p>
            </PageCard>
          )}
        </PageCard>
      </div>
    </div>
  );
}
