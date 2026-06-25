const INVALID_NARRATIVES = new Set(["d", "ok", "none", "null", "-", "..."]);

export function isRenderableNarrative(value?: string | null): value is string {
  const text = String(value ?? "").trim();
  if (text.length < 12) return false;
  if (INVALID_NARRATIVES.has(text.toLowerCase())) return false;
  if (!/[A-Za-zÀ-ỹ]/.test(text)) return false;
  if (/^[\W_]+$/u.test(text)) return false;
  return /\s/.test(text) || /[.:;,\-–]/.test(text);
}
