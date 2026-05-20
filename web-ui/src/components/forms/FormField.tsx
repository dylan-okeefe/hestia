import React from 'react';
import './FormField.css';

interface FormFieldProps {
  label: string;
  error?: string;
  children: React.ReactNode;
  required?: boolean;
}

export default function FormField({ label, error, children, required }: FormFieldProps) {
  return (
    <div className="form-field">
      <label className="form-field__label">
        {label}
        {required && <span className="form-field__required">*</span>}
      </label>
      <div className={error ? 'form-field__input--error' : ''}>
        {children}
      </div>
      {error && <span className="form-field__error">{error}</span>}
    </div>
  );
}
