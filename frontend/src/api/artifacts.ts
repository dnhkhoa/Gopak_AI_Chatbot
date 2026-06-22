import { API_BASE_URL } from "./http";

export const artifactUrl = (artifactId: string) =>
  `${API_BASE_URL}/artifacts/${encodeURIComponent(artifactId)}/download`;
