import type { Citation } from "@/types/api";
interface AnswerPanelProps {
  answer: string;
  citations: Citation[];
}

// Not a link: there is no route or API endpoint that serves a single document,
// so linking to /documents/:id sent every source to a 404. A citation a lawyer
// cannot follow is bad; one that promises to be followable and then breaks is
// worse. Restore the anchor once a document view exists.
function CitationRow({ citation, index }: { citation: Citation; index: number }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2 px-3 rounded-md border border-border text-sm text-muted">
      <span className="min-w-0">
        <span className="text-faint mr-2">[{index + 1}]</span>
        <span className="break-all">{citation.document_name}</span>
      </span>
      <span className="text-faint shrink-0">Page {citation.page_number}</span>
    </div>
  );
}

export function AnswerPanel({ answer, citations }: AnswerPanelProps) {
  return (
    <div className="flex flex-col gap-4">
      <div className="bg-surface border border-border rounded-lg px-5 py-4">
        <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">
          {answer}
        </p>
      </div>

      {citations.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium text-subtle uppercase tracking-wide">
            Sources
          </p>
          {citations.map((citation, index) => (
            <CitationRow
              key={`${citation.document_id}-${citation.page_number}-${index}`}
              citation={citation}
              index={index}
            />
          ))}
        </div>
      )}
    </div>
  );
}


