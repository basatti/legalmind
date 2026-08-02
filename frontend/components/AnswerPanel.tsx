interface Citation {
  document_id: number;
  page_number: number;
}

interface AnswerPanelProps {
  answer: string;
  citations: Citation[];
}

function CitationRow({ citation, index }: { citation: Citation; index: number }) {
  return (
    <a
      href={`/documents/${citation.document_id}`}
      className="flex items-center justify-between py-2 px-3 rounded-md border border-neutral-200 text-sm text-neutral-700 hover:border-neutral-400 hover:bg-neutral-50 transition-colors"
    >
      <span>
        <span className="text-neutral-400 mr-2">[{index + 1}]</span>
        Document #{citation.document_id}
      </span>
      <span className="text-neutral-400">Page {citation.page_number}</span>
    </a>
  );
}

export function AnswerPanel({ answer, citations }: AnswerPanelProps) {
  return (
    <div className="flex flex-col gap-4">
      <div className="bg-white border border-neutral-200 rounded-lg px-5 py-4">
        <p className="text-sm text-neutral-900 leading-relaxed whitespace-pre-wrap">
          {answer}
        </p>
      </div>

      {citations.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide">
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

