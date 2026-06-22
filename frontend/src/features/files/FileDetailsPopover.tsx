import { FileSpreadsheet, Trash2, X } from "lucide-react";
import { formatBytes, type UploadedFile } from "../../types/files";

const STATUS_LABEL: Record<UploadedFile["status"], string> = {
  uploaded: "Uploaded",
  uploading: "Uploading",
  processing: "Processing",
  ready: "Ready",
  failed: "Failed",
  deleting: "Deleting"
};

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail-row">
      <span className="detail-label">{label}</span>
      <span className="detail-value">{value}</span>
    </div>
  );
}

interface Props {
  file: UploadedFile;
  onClose: () => void;
  onRemove: () => void;
}

export function FileDetailsPopover({ file, onClose, onRemove }: Props) {
  return (
    <div className="file-details" role="dialog" aria-label={`Details for ${file.filename}`}>
      <div className="file-details-head">
        <div className="file-icon" aria-hidden="true">
          <FileSpreadsheet size={18} />
        </div>
        <span className="file-details-title" title={file.filename}>
          {file.filename}
        </span>
        <button className="file-remove" aria-label="Close details" onClick={onClose}>
          <X size={16} />
        </button>
      </div>

      <div className="file-details-body">
        <Row label="File name" value={file.filename} />
        <Row label="Size" value={formatBytes(file.size_bytes)} />
        <Row label="Status" value={STATUS_LABEL[file.status]} />
        {file.processing_stage ? <Row label="Stage" value={file.processing_stage} /> : null}
        {file.progress != null ? <Row label="Progress" value={`${file.progress}%`} /> : null}
        {file.uploaded_at ? <Row label="Uploaded" value={new Date(file.uploaded_at).toLocaleString("en-US")} /> : null}
        {file.row_count != null ? <Row label="Rows" value={file.row_count.toLocaleString("en-US")} /> : null}
        {file.sheet_count != null ? <Row label="Sheets" value={String(file.sheet_count)} /> : null}
        {file.table_count != null ? <Row label="Tables" value={String(file.table_count)} /> : null}
        {file.status === "failed" && (file.error_message || file.error) ? (
          <Row label="Error" value={file.error_message || (typeof file.error === "string" ? file.error : file.error?.message || "Upload failed")} />
        ) : null}
      </div>

      <div className="file-details-foot">
        <button
          className="btn-danger"
          onClick={() => {
            const inUse = file.status === "ready";
            if (!inUse || window.confirm(`Remove "${file.filename}"? It may be in use by the assistant.`)) {
              onRemove();
            }
          }}
        >
          <Trash2 size={15} /> Remove file
        </button>
      </div>
    </div>
  );
}
