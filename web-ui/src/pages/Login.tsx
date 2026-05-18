import { useState, useEffect, useRef } from 'react';
import { fetchAvailableUsers, requestCode, verifyCode } from '../api/client';
import { useAuth } from '../context/AuthContext';
import PageCard from '../components/layout/PageCard';
import EmptyState from '../components/layout/EmptyState';
import { label, ROLE_LABELS } from '../lib/labels';
import { TEXT } from '../lib/text';
import './Login.css';

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

  const steps = [TEXT.login.step1Label, TEXT.login.step2Label, TEXT.login.step3Label];
  const currentStepIndex = phase === 'select-user' ? 0 : phase === 'select-platform' ? 1 : 2;

  return (
    <div className="login-page">
      <div className="login-card">
        <h1 className="login-title">{TEXT.login.title}</h1>
        <p className="login-subtitle">{TEXT.login.subtitle}</p>

        {/* Progress indicator */}
        <div className="login-stepper">
          {steps.map((step, index) => (
            <div key={step} className="login-stepper__item">
              <div
                className={
                  index <= currentStepIndex
                    ? 'login-stepper__circle login-stepper__circle--active'
                    : 'login-stepper__circle login-stepper__circle--inactive'
                }
              >
                {index + 1}
              </div>
              <span
                className={
                  'login-stepper__label ' +
                  (index <= currentStepIndex ? 'login-stepper__label--active' : 'login-stepper__label--inactive') +
                  (index === currentStepIndex ? ' login-stepper__label--current' : '')
                }
              >
                {step}
              </span>
            </div>
          ))}
        </div>

        {phase === 'select-user' && (
          <div className="login-step">
            <p className="login-description">{TEXT.login.step1Description}</p>
            {loadingUsers && <EmptyState title={TEXT.login.loadingTitle} description={TEXT.login.loadingDescription} />}
            {!loadingUsers && availableUsers.length === 0 && (
              <EmptyState
                title={TEXT.login.noUsersTitle}
                description={TEXT.login.noUsersDescription}
              />
            )}
            <div className="login-grid">
              {!loadingUsers && availableUsers.map((user) => (
                <button
                  key={user.user_id}
                  onClick={() => handleSelectUser(user)}
                  className="login-user-card"
                >
                  <span style={{ fontWeight: 'bold' }}>{user.display_name}</span>
                  <span
                    className="login-role-badge"
                    style={{ background: roleBadgeColor(user.role) }}
                  >
                    {label(ROLE_LABELS, user.role)}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {phase === 'select-platform' && selectedUser && (
          <div className="login-step">
            <p className="login-description">
              {TEXT.login.selectedUserPrefix}<strong>{selectedUser.display_name}</strong>
            </p>
            {selectedUser.platforms.length === 0 && (
              <EmptyState
                title={TEXT.login.noPlatformsTitle}
                description={TEXT.login.noPlatformsDescription}
              />
            )}
            <div className="stack-md">
              {selectedUser.platforms.map((platform) => (
                <button
                  key={platform}
                  onClick={() => handleRequestCode(platform)}
                  disabled={sending}
                  className="login-platform-btn"
                >
                  <div className="login-platform-btn__title">
                    {sending && selectedPlatform === platform
                      ? TEXT.common.sending
                      : TEXT.login.sendCodeVia(platform)}
                  </div>
                  <div className="login-platform-btn__helper">
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
              className="login-back-btn"
            >
              {TEXT.login.backToUserSelection}
            </button>
          </div>
        )}

        {phase === 'input' && (
          <div className="login-step">
            <p className="login-description">
              {TEXT.login.enterCodePrefix}<strong>{selectedPlatform}</strong>
            </p>
            <input
              type="text"
              inputMode="numeric"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder={TEXT.login.codePlaceholder}
              className="login-code-input"
            />
            <div className="login-footer">
              <span className={expiresIn > 0 ? 'login-timer--active' : 'login-timer--expired'}>
                {expiresIn > 0 ? TEXT.login.expiresIn(formatTime(expiresIn)) : TEXT.login.codeExpired}
              </span>
              <button onClick={handleVerify} disabled={verifying || code.length < 6 || expiresIn <= 0}>
                {verifying ? TEXT.common.verifying : TEXT.login.verify}
              </button>
            </div>
            <button
              onClick={() => {
                setPhase('select-platform');
                setCode('');
                if (timerRef.current) clearInterval(timerRef.current);
              }}
              className="login-back-btn"
            >
              {TEXT.login.backToPlatformSelection}
            </button>
            {expiresIn <= 0 && (
              <p className="text-small text-secondary">
                {TEXT.login.codeExpiredPrefix}{' '}
                <button
                  onClick={() => {
                    setPhase('select-platform');
                    setCode('');
                    if (timerRef.current) clearInterval(timerRef.current);
                  }}
                  className="login-resend-btn"
                >
                  {TEXT.login.resend}
                </button>
              </p>
            )}
          </div>
        )}

        {error && (
          <PageCard className="login-error-card">
            <p className="login-error-text">{error}</p>
          </PageCard>
        )}
      </div>
    </div>
  );
}
