import { AlertCircle, ChevronDown, FileSpreadsheet, RotateCcw } from "lucide-react";
import { useState } from "react";
import type { UseFiles } from "../../hooks/useFiles";
import { formatBytes } from "../../types/files";
import { FileDetailsPopover } from "./FileDetailsPopover";
import { FileUploadDropzone } from "./FileUploadDropzone";
import { UploadedFileItem } from "./UploadedFileItem";

export function UploadedFilesPanel({
  files,
  activeFileId = null,
  onSelectActive = () => undefined
}: {
  files: UseFiles;
  activeFileId?: string | null;
  onSelectActive?: (fileId: string) => void;
}) {
  const [open, setOpen] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const totalBytes = files.files.reduce((sum, f) => sum + f.size_bytes, 0);
  const selectedFile = files.files.find((f) => f.id === selectedId) ?? null;
  const displaySelectedId = activeFileId ?? selectedId;

  const closeDetails = () => setDetailsOpen(false);

  return (
    <>
      <section className={`files-panel ${open ? "open" : "collapsed"}`} aria-label="Uploaded files">
        <button className="files-header" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
          <span className="files-title">
            <FileSpreadsheet size={16} />
            Uploaded files
          </span>
          <span className="files-count">{files.files.length}</span>
          <ChevronDown size={16} className={`files-chevron ${open ? "up" : ""}`} />
        </button>

        {open ? (
          <div className="files-body">
            <FileUploadDropzone onFiles={(list) => void files.upload(list)} />

            {files.error ? (
              <div className="files-alert" role="alert">
                <AlertCircle size={14} />
                <span>{files.error}</span>
                <button className="files-retry" onClick={() => void files.retry()} aria-label="Retry upload">
                  <RotateCcw size={13} /> Retry
                </button>
              </div>
            ) : null}

            {files.files.length ? (
              <ul className="files-list">
                {files.files.map((file) => (
                  <li key={file.id}>
                    <UploadedFileItem
                      file={file}
                      selected={file.id === displaySelectedId}
                      using={file.id === activeFileId}
                      onSelect={() => {
                        setSelectedId(file.id);
                        if (file.status === "ready") onSelectActive(file.id);
                      }}
                      onViewDetails={() => {
                        setSelectedId(file.id);
                        setDetailsOpen(true);
                      }}
                      onRemove={() => {
                        if (selectedId === file.id) closeDetails();
                        void files.remove(file.id);
                      }}
                    />
                  </li>
                ))}
              </ul>
            ) : (
              <div className="files-empty">{files.loading ? "Loading files…" : "No files uploaded yet."}</div>
            )}

            {files.files.length ? (
              <div className="files-footer">
                <span>{files.files.length} file{files.files.length === 1 ? "" : "s"} uploaded</span>
                <span>{formatBytes(totalBytes)} total</span>
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      {detailsOpen && selectedFile ? (
        <FileDetailsPopover
          file={selectedFile}
          onClose={closeDetails}
          onRemove={() => {
            closeDetails();
            void files.remove(selectedFile.id);
          }}
        />
      ) : null}
    </>
  );
}
