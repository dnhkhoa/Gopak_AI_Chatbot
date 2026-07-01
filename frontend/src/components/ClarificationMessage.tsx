import { NarrativeBlock } from "./NarrativeBlock";

export function ClarificationMessage({ text }: { text: string }) {
  return <div className="soft-notice"><NarrativeBlock text={text} /></div>;
}
