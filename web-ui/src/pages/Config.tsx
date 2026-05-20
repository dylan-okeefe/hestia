import { useEffect, useState } from 'react';
import { fetchConfig } from '../api/client';
import ConfigForm from '../components/ConfigForm';
import './Config.css';

export default function Config() {
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchConfig()
      .then((data) => {
        setConfig(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <div className="config-page">
      <h1>Configuration</h1>
      {loading && <p>Loading configuration…</p>}
      {error && <p className="text-danger">{error}</p>}
      {config && <ConfigForm initialConfig={config} />}
    </div>
  );
}
