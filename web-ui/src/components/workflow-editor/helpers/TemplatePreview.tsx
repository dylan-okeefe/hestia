import { TEXT } from '../../../lib/text';
import HighlightPreview from './HighlightPreview';
import './TemplatePreview.css';

interface TemplatePreviewProps {
  message: string;
}

export default function TemplatePreview({ message }: TemplatePreviewProps) {
  const count = message.length;
  const countClass =
    count > 4096
      ? 'template-preview__count--danger'
      : count > 4000
      ? 'template-preview__count--warning'
      : 'template-preview__count--normal';

  return (
    <div className="template-preview">
      <div className="template-preview__label">{TEXT.workflowEditor.previewLabel}</div>
      <HighlightPreview text={message} />
      <div className={`template-preview__count ${countClass}`}>
        {TEXT.workflowEditor.characterCount(count)}
        {count > 4096 && TEXT.workflowEditor.exceedsTelegramLimit}
        {count > 4000 && count <= 4096 && TEXT.workflowEditor.mayExceedTelegramLimit}
      </div>
    </div>
  );
}
