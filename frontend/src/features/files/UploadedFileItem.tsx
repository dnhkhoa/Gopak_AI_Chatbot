import { Eye, FileSpreadsheet, Loader2, MoreHorizontal, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { formatBytes, type UploadedFile } from "../../types/files";

const STATUS_LABEL: Record<UploadedFile["status"], string> = {
  uploading: "Uploading",
  processing: "Processing",
  ready: "Ready",
  failed: "Failed"
};

interface Props {
  file: UploadedFile;
  selected: boolean;
  onSelect: () => void;
  onViewDetails: () => void;
  onRemove: () => void;
}

export function UploadedFileItem({ file, selected, onSelect, onViewDetails, onRemove }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const busy = file.status === "uploading" || file.status === "processing";

  useEffect(() => {
    if (!menuOpen) return;
    const onAway = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onAway);
    return () => document.removeEventListener("mousedown", onAway);
  }, [menuOpen]);

  const confirmRemove = () => {
    const inUse = file.status === "ready";
    if (!inUse || window.confirm(`Remove "${file.filename}"? It may be in use by the assistant.`)) {
      onRemove();
    }
  };

  return (
    <div ref={rootRef} className="file-item-wrap">
      <div
        className={`file-item ${selected ? "selected" : ""}`}
        role="button"
        tabIndex={0}
        aria-selected={selected}
        aria-label={`${file.filename}, ${formatBytes(file.size_bytes)}, ${STATUS_LABEL[file.status]}`}
        onClick={onSelect}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onViewDetails();
          }
        }}
      >
        <div className="file-icon" aria-hidden="true">
          <FileSpreadsheet size={20} />
        </div>

        <div className="file-main">
          <span className="file-name" title={file.filename}>
            {file.filename}
          </span>
          <span className="file-meta">
            <span className="file-size">{formatBytes(file.size_bytes)}</span>
            <span className="file-dot" aria-hidden="true">·</span>
            <span className={`file-status status-${file.status}`}>
              {busy ? <Loader2 size={12} className="spin" /> : null}
              {STATUS_LABEL[file.status]}
            </span>
          </span>
        </div>

        <button
          className="file-menu-btn"
          aria-label={`Options for ${file.filename}`}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          onClick={(event) => {
            event.stopPropagation();
            setMenuOpen((open) => !open);
          }}
        >
          <MoreHorizontal size={16} />
        </button>
      </div>

      {menuOpen ? (
        <div className="file-menu" role="menu">
          <button
            className="menu-item"
            role="menuitem"
            onClick={() => {
              setMenuOpen(false);
              onViewDetails();
            }}
          >
            <Eye size={15} /> View details
          </button>
          <button
            className="menu-item danger"
            role="menuitem"
            onClick={() => {
              setMenuOpen(false);
              confirmRemove();
            }}
          >
            <Trash2 size={15} /> Remove file
          </button>
        </div>
      ) : null}
    </div>
  );
}
