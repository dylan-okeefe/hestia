import Modal from '../Modal';
import Button from '../Button';
import type { AllowListDiff } from '../../api/client';
import './AllowListDiffDialog.css';

export interface AllowListDiffDialogProps {
  isOpen: boolean;
  diff: AllowListDiff | null;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}

/** L245: shown when activating a version would change the workflow's
 * authorized tools. Activation proceeds only after explicit confirmation
 * of the diff. */
export default function AllowListDiffDialog({
  isOpen,
  diff,
  onConfirm,
  onCancel,
  loading = false,
}: AllowListDiffDialogProps) {
  if (!diff) return null;
  const hasAdded = diff.added.length > 0;
  const hasRemoved = diff.removed.length > 0;

  return (
    <Modal isOpen={isOpen} onClose={onCancel} title="Review authorization changes" size="sm">
      <p className="text-small text-secondary">
        This version changes the tools the workflow is allowed to use.
        Review the change before it becomes live for unattended runs.
      </p>
      {hasAdded && (
        <div className="aldiff__section">
          <strong className="aldiff__heading aldiff__heading--added">Newly allowed</strong>
          <ul className="aldiff__list">
            {diff.added.map((tool) => (
              <li key={tool} className="aldiff__item aldiff__item--added">
                {tool}
              </li>
            ))}
          </ul>
        </div>
      )}
      {hasRemoved && (
        <div className="aldiff__section">
          <strong className="aldiff__heading aldiff__heading--removed">No longer allowed</strong>
          <ul className="aldiff__list">
            {diff.removed.map((tool) => (
              <li key={tool} className="aldiff__item aldiff__item--removed">
                {tool}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="row-center gap-2 mt-4">
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button variant="primary" onClick={onConfirm} loading={loading}>
          Confirm &amp; activate
        </Button>
      </div>
    </Modal>
  );
}
