import { NarrativeBlock } from "./NarrativeBlock";

export function RefusalMessage({ text }: { text: string }) {
  return <div className="soft-notice"><NarrativeBlock text={text} /></div>;
}
