/**
 * ArtifactModal — preview a file/artifact/checkpoint path. Content is produced
 * by the pure lib (makeArtifactPreview); this component is presentational only.
 */
export default function ArtifactModal({
  path,
  content,
  onClose,
}: {
  path: string;
  content: string;
  onClose: () => void;
}) {
  return (
    <div className="leg-modal-backdrop" data-testid="artifact-modal" onClick={onClose}>
      <div className="leg-modal" onClick={(e) => e.stopPropagation()}>
        <div className="leg-modal-head">
          <div className="leg-modal-title" data-testid="artifact-modal-title">{path}</div>
          <button className="leg-close" onClick={onClose}>Close</button>
        </div>
        <pre className="leg-modal-body">{content}</pre>
      </div>
    </div>
  );
}
