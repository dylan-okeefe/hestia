import { useState } from 'react';
import { TEXT } from '../../../lib/text';
import './JsonTextarea.css';

interface JsonTextareaProps {
  value: object;
  onChange: (v: object) => void;
  rows: number;
  label: string;
  validate?: boolean;
  placeholder?: string;
}

export default function JsonTextarea({
  value,
  onChange,
  rows,
  label,
  validate,
  placeholder,
}: JsonTextareaProps) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [error, setError] = useState<string | null>(null);

  const handleBlur = () => {
    if (!validate) {
      try {
        onChange(JSON.parse(text));
        setError(null);
      } catch {
        // ignore invalid JSON
      }
      return;
    }
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        setError(TEXT.workflowEditor.headersObjectError);
        return;
      }
      onChange(parsed);
      setError(null);
    } catch {
      setError(TEXT.workflowEditor.invalidJsonError);
    }
  };

  return (
    <div className="json-textarea">
      <label className="json-textarea__label">{label}</label>
      <textarea
        rows={rows}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={handleBlur}
        placeholder={placeholder}
        className={`json-textarea__field${error ? ' json-textarea__field--error' : ''}`}
        aria-invalid={error ? 'true' : 'false'}
      />
      {error && <span className="json-textarea__error">{error}</span>}
    </div>
  );
}
