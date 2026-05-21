import { useState } from 'react';
import { TEXT } from '../../../lib/text';
import './SyntaxHelp.css';

export default function SyntaxHelp() {
  const [open, setOpen] = useState(false);
  return (
    <div className="syntax-help">
      <button
        onClick={() => setOpen((o) => !o)}
        className="syntax-help__toggle"
      >
        {open ? TEXT.workflowEditor.hideSyntaxHelp : TEXT.workflowEditor.showSyntaxHelp}
      </button>
      {open && (
        <div className="syntax-help__content">
          <p><strong>{TEXT.workflowEditor.syntaxHelpVariables}</strong> {TEXT.workflowEditor.syntaxHelpVariablesValue}</p>
          <p><strong>{TEXT.workflowEditor.syntaxHelpComparisons}</strong> {TEXT.workflowEditor.syntaxHelpComparisonsValue}</p>
          <p><strong>{TEXT.workflowEditor.syntaxHelpLogic}</strong> {TEXT.workflowEditor.syntaxHelpLogicValue}</p>
          <p><strong>{TEXT.workflowEditor.syntaxHelpArithmetic}</strong> {TEXT.workflowEditor.syntaxHelpArithmeticValue}</p>
          <p><strong>{TEXT.workflowEditor.syntaxHelpLiterals}</strong> {TEXT.workflowEditor.syntaxHelpLiteralsValue}</p>
          <p><strong>{TEXT.workflowEditor.syntaxHelpExamples}</strong> {TEXT.workflowEditor.syntaxHelpExamplesValue}</p>
        </div>
      )}
    </div>
  );
}
