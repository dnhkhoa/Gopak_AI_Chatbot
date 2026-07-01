import { NarrativeBlock } from "./NarrativeBlock";

export function ErrorMessage({ text, onRetry }: { text: string; onRetry?: () => void }) {
  return (
    <div className="error-message">
      <NarrativeBlock text={text} />
      {onRetry ? <button onClick={onRetry}>Thử lại</button> : null}
    </div>
  );
}
