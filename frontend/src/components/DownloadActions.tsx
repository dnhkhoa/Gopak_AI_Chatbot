import { Download } from "lucide-react";
import { api } from "../api/client";
import type { DownloadPayload } from "../types/api";

export function DownloadActions({ downloads }: { downloads: DownloadPayload[] }) {
  if (!downloads.length) {
    return null;
  }
  return (
    <div className="download-actions">
      {downloads.map((item) => (
        <a key={item.id} href={api.artifactUrl(item.id)}>
          <Download size={16} />
          {item.label}
        </a>
      ))}
    </div>
  );
}
