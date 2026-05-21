import './HighlightPreview.css';

interface HighlightPreviewProps {
  text: string;
}

export default function HighlightPreview({ text }: HighlightPreviewProps) {
  const parts = text.split(/(\{[^}]+\})/g);
  return (
    <div className="highlight-preview">
      {parts.map((part, i) =>
        part.match(/\{[^}]+\}/) ? (
          <span key={i} className="highlight-preview__variable">
            {part}
          </span>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </div>
  );
}
