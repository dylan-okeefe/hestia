import { useState } from 'react';
import DoctorCheckList from '../components/DoctorCheckList';
import AuditFindings from '../components/AuditFindings';
import EgressLog from '../components/EgressLog';

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

export default function Security() {
  const [checks, setChecks] = useState<Check[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);

  return (
    <div style={{ padding: '1rem' }}>
      <h1>Security &amp; Health</h1>
      <section style={{ marginBottom: '2rem' }}>
        <DoctorCheckList checks={checks} onRefresh={setChecks} />
      </section>
      <section style={{ marginBottom: '2rem' }}>
        <AuditFindings findings={findings} onRefresh={setFindings} />
      </section>
      <section>
        <EgressLog />
      </section>
    </div>
  );
}
