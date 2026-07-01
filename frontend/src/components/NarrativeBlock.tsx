export function NarrativeBlock({ text }: { text?: string | null }) {
  const value = (text ?? "").trim();
  if (!value) {
    return null;
  }
  const blocks = value.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean);
  return (
    <div className="narrative-block">
      {blocks.map((block, index) => {
        const lines = block.split(/\n/).map((line) => line.trim()).filter(Boolean);
        const bulletLines = lines.filter((line) => line.startsWith("- "));
        if (bulletLines.length === lines.length && lines.length > 0) {
          return (
            <ul key={`${block}-${index}`}>
              {lines.map((line) => (
                <li key={line}>{line.replace(/^- /, "")}</li>
              ))}
            </ul>
          );
        }
        if (lines.length > 1) {
          return (
            <div key={`${block}-${index}`} className="narrative-section">
              {lines.map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>
          );
        }
        return <p key={`${block}-${index}`}>{block}</p>;
      })}
    </div>
  );
}
