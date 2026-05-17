import { useState } from 'react';
import DoctorCheckList from '../components/DoctorCheckList';
import AuditFindings from '../components/AuditFindings';
import EgressLog from '../components/EgressLog';
import PageCard from '../components/layout/PageCard';

interface Check {
  name: string;
  ok: boolean;
  detail: string;
}

interface Finding {
  severity: 'critical' | 'warning' | 'info';
  category: string;
  message: string;
  details: Record<string, unknown>;
}

type AuditTab = 'all' | 'warnings' | 'info';

export default function Security() {
  const [checks, setChecks] = useState<Check[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [auditTab, setAuditTab] = useState<AuditTab>('all');

  const filteredFindings = findings.filter((f) => {
    if (auditTab === 'all') return true;
    if (auditTab === 'warnings') return f.severity === 'critical' || f.severity === 'warning';
    if (auditTab === 'info') return f.severity === 'info';
    return true;
  });

  return (
    <div style={{ padding: '1rem' }}>
      <h1 style={{ marginBottom: '1rem' }}>Security &amp; Health</h1>

      <section style={{ marginBottom: '2rem' }}>
        <DoctorCheckList checks={checks} onRefresh={setChecks} />
      </section>

      <section style={{ marginBottom: '2rem' }}>
        <PageCard>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
            <h2 style={{ margin: 0 }}>Audit Findings</h2>
            <div style={{ display: 'flex', gap: '0.25rem' }}>
              {(['all', 'warnings', 'info'] as AuditTab[]).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setAuditTab(tab)}
                  style={{
                    padding: '0.25rem 0.5rem',
                    fontSize: '0.8rem',
                    fontWeight: auditTab === tab ? 600 : 400,
                    borderBottom: auditTab === tab ? '2px solid #1976d2' : '2px solid transparent',
                    background: 'transparent',
                    border: 'none',
                    borderRadius: 0,
                    cursor: 'pointer',
                  }}
                >
                  {tab.charAt(0).toUpperCase() + tab.slice(1)}
                </button>
              ))}
            </div>
          </div>
          <AuditFindings findings={filteredFindings} onRefresh={setFindings} />
        </PageCard>
      </section>

      <section>
        <PageCard>
          <EgressLog />
        </PageCard>
      </section>
    </div>
  );
}
