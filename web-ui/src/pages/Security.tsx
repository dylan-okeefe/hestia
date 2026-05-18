import { useState } from 'react';
import DoctorCheckList from '../components/DoctorCheckList';
import AuditFindings from '../components/AuditFindings';
import EgressLog from '../components/EgressLog';
import PageCard from '../components/layout/PageCard';
import { TEXT } from '../lib/text';
import './Security.css';

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
    <div className="security-page">
      <h1 className="security-title">{TEXT.security.title}</h1>

      <section className="security-section">
        <DoctorCheckList checks={checks} onRefresh={setChecks} />
      </section>

      <section className="security-section">
        <PageCard>
          <div className="row-between mb-3" style={{ flexWrap: 'wrap', gap: 'var(--space-2)' }}>
            <h2 style={{ margin: 0 }}>{TEXT.security.auditFindingsTitle}</h2>
            <div className="row-sm">
              {(['all', 'warnings', 'info'] as AuditTab[]).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setAuditTab(tab)}
                  className={auditTab === tab ? 'tab-btn tab-btn--active' : 'tab-btn'}
                >
                  {tab === 'all' ? TEXT.security.tabAll : tab === 'warnings' ? TEXT.security.tabWarnings : TEXT.security.tabInfo}
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
