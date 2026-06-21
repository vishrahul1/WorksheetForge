"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { documentsApi, runsApi } from "@/lib/api";
import { Loader2, FileText, ClipboardList, X, ChevronDown, ChevronRight } from "lucide-react";
import type { RunPhase } from "@/types";

interface Props {
  runId: string;
  documentId: string;
}

// ─── Log Modal ────────────────────────────────────────────────────────────────

function PhaseLogRow({ phase }: { phase: RunPhase }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"input" | "output">("input");

  const label = phase.phase_name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const statusColour =
    phase.status === "done" ? "text-green-600" :
    phase.status === "failed" ? "text-red-600" :
    "text-gray-500";

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      {/* Header row */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
      >
        <div className="flex items-center gap-3">
          {open ? <ChevronDown className="h-4 w-4 text-gray-400" /> : <ChevronRight className="h-4 w-4 text-gray-400" />}
          <span className="text-sm font-medium text-gray-900">{label}</span>
          <span className={`text-xs font-medium ${statusColour}`}>{phase.status}</span>
        </div>
        <span className="text-xs text-muted-foreground">
          {phase.tokens_in > 0 && `${phase.tokens_in.toLocaleString()} in / ${phase.tokens_out.toLocaleString()} out`}
        </span>
      </button>

      {/* Content */}
      {open && (
        <div className="border-t border-gray-200">
          {/* Tab switcher */}
          <div className="flex border-b border-gray-200">
            <button
              onClick={() => setTab("input")}
              className={`px-4 py-2 text-xs font-medium transition-colors ${
                tab === "input"
                  ? "border-b-2 border-primary text-primary"
                  : "text-muted-foreground hover:text-gray-700"
              }`}
            >
              Input (Prompt Sent)
            </button>
            <button
              onClick={() => setTab("output")}
              className={`px-4 py-2 text-xs font-medium transition-colors ${
                tab === "output"
                  ? "border-b-2 border-primary text-primary"
                  : "text-muted-foreground hover:text-gray-700"
              }`}
            >
              Output (AI Response)
            </button>
          </div>

          {/* Text content */}
          <div className="p-4">
            <pre className="text-xs text-gray-800 whitespace-pre-wrap break-words font-mono bg-gray-50 p-3 rounded-md max-h-96 overflow-y-auto">
              {tab === "input"
                ? (phase.prompt_sent || "(No prompt recorded for this phase)")
                : (phase.output || "(No output recorded)")
              }
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

function LogModal({ runId, onClose }: { runId: string; onClose: () => void }) {
  const { data: phases, isLoading } = useQuery({
    queryKey: ["run-phases", runId],
    queryFn: () => runsApi.getPhases(runId),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col m-4">
        {/* Modal header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <ClipboardList className="h-5 w-5 text-primary" />
            <h2 className="text-base font-semibold text-gray-900">AI Generation Log</h2>
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-gray-700 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Phase list */}
        <div className="flex-1 overflow-y-auto p-6 space-y-3">
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          )}
          {phases?.map((phase) => (
            <PhaseLogRow key={phase.id} phase={phase} />
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Main preview component ───────────────────────────────────────────────────

export function GenerationPreview({ runId, documentId }: Props) {
  const [showLog, setShowLog] = useState(false);

  const { data: content, isLoading } = useQuery({
    queryKey: ["doc-preview", documentId],
    queryFn: () => documentsApi.getContent(documentId),
  });

  return (
    <>
      {/* Preview panel */}
      <div className="mt-6 border border-gray-200 rounded-xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" />
            <span className="text-sm font-semibold text-gray-900">Generated Worksheet Preview</span>
          </div>
          <button
            onClick={() => setShowLog(true)}
            className="flex items-center gap-1.5 text-xs font-medium text-gray-600 hover:text-gray-900 border border-gray-200 rounded-md px-3 py-1.5 hover:bg-white transition-colors"
          >
            <ClipboardList className="h-3.5 w-3.5" />
            View Log
          </button>
        </div>

        {/* Content */}
        <div className="bg-white max-h-[600px] overflow-y-auto p-6">
          {isLoading && (
            <div className="flex items-center justify-center py-12 gap-2 text-muted-foreground text-sm">
              <Loader2 className="h-5 w-5 animate-spin" />
              Loading preview...
            </div>
          )}
          {content && (
            <div
              className="prose prose-sm max-w-none"
              dangerouslySetInnerHTML={{ __html: content.html }}
            />
          )}
        </div>
      </div>

      {/* Log modal */}
      {showLog && <LogModal runId={runId} onClose={() => setShowLog(false)} />}
    </>
  );
}
