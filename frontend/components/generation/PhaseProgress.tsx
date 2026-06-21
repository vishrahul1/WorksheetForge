"use client";

import { useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { CheckCircle, Circle, Loader2, XCircle, Clock, StopCircle } from "lucide-react";
import type { SSEEvent } from "@/types";
import { toast } from "@/components/ui/toaster";
import { runsApi } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface PhaseState {
  name: string;
  label: string;   // display label — from SSE event or fallback to name
  order: number;
  status: "queued" | "running" | "done" | "failed";
}

interface Props {
  runId: string;
  onComplete: (documentId: string) => void;
}

// Static labels for fixed phases; dynamic section labels come from SSE events
const FIXED_PHASE_LABELS: Record<string, string> = {
  source_audit:      "Auditing source material",
  worksheet_skeleton: "Planning worksheet structure",
  assemble_docx:     "Assembling final document",
};

export function PhaseProgress({ runId, onComplete }: Props) {
  const { data: session } = useSession();
  const [phases, setPhases] = useState<PhaseState[]>([]);
  const [runStatus, setRunStatus] = useState<
    "connecting" | "running" | "completed" | "failed"
  >("connecting");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [currentPhase, setCurrentPhase] = useState<string | null>(null);
  const [tokensSummary, setTokensSummary] = useState<{
    in: number;
    out: number;
    cost: number;
  } | null>(null);
  const [totalPhasesFromServer, setTotalPhasesFromServer] = useState<number>(8);
  const [cancelling, setCancelling] = useState(false);
  const startTimeRef = useRef<number>(Date.now());
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!session?.accessToken) return;

    startTimeRef.current = Date.now();
    timerRef.current = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startTimeRef.current) / 1000));
    }, 1000);

    // EventSource can't send headers — pass token as query param
    const es = new EventSource(
      `${API_URL}/runs/${runId}/stream?token=${encodeURIComponent(session.accessToken)}`
    );
    eventSourceRef.current = es;

    es.onmessage = (e) => {
      try {
        const event: SSEEvent = JSON.parse(e.data);
        handleEvent(event);
      } catch {}
    };

    es.onerror = () => {
      setRunStatus("failed");
      cleanup();
    };

    return () => cleanup();
  // Re-run when runId changes OR when the session token becomes available
  }, [runId, session?.accessToken]);

  const cleanup = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  };

  const handleCancel = async () => {
    if (cancelling) return;
    setCancelling(true);
    try {
      await runsApi.cancel(runId);
      cleanup();
      setRunStatus("failed");
      toast({ title: "Generation cancelled", variant: "destructive" });
    } catch (err: any) {
      toast({
        title: "Could not cancel",
        description: err.message || "The run may have already completed.",
        variant: "destructive",
      });
    } finally {
      setCancelling(false);
    }
  };

  const handleEvent = (event: SSEEvent) => {
    switch (event.type) {
      case "run_started":
        setRunStatus("running");
        break;

      case "phase_started":
        if (event.total_phases) setTotalPhasesFromServer(event.total_phases);
        setCurrentPhase(event.phase || null);
        setPhases((prev) => {
          const label =
            event.phase_label ||
            FIXED_PHASE_LABELS[event.phase!] ||
            event.phase!;
          const exists = prev.find((p) => p.name === event.phase);
          if (exists) {
            return prev.map((p) =>
              p.name === event.phase ? { ...p, status: "running", label } : p
            );
          }
          return [
            ...prev,
            {
              name: event.phase!,
              label,
              order: event.phase_order ?? prev.length,
              status: "running",
            },
          ];
        });
        break;

      case "phase_completed":
        if (event.total_phases) setTotalPhasesFromServer(event.total_phases);
        setPhases((prev) => {
          const label =
            event.phase_label ||
            FIXED_PHASE_LABELS[event.phase!] ||
            event.phase!;
          const exists = prev.find((p) => p.name === event.phase);
          if (exists) {
            return prev.map((p) =>
              p.name === event.phase ? { ...p, status: "done", label } : p
            );
          }
          // Skipped phases (already done from a retry) arrive only as completed
          return [
            ...prev,
            {
              name: event.phase!,
              label,
              order: event.phase_order ?? prev.length,
              status: "done",
            },
          ];
        });
        break;

      case "phase_failed": {
        const failedLabel =
          event.phase_label ||
          FIXED_PHASE_LABELS[event.phase!] ||
          event.phase!;
        const errorDetail = event.error || "Unknown error";
        const isRateLimit =
          errorDetail.toLowerCase().includes("rate limit") ||
          errorDetail.includes("429");

        toast({
          title: isRateLimit
            ? `Rate limit hit — ${failedLabel}`
            : `Phase failed — ${failedLabel}`,
          description: isRateLimit
            ? "The AI provider rate limit was reached. Retrying automatically…"
            : errorDetail.slice(0, 150),
          variant: "destructive",
        });

        setPhases((prev) =>
          prev.map((p) =>
            p.name === event.phase ? { ...p, status: "failed" } : p
          )
        );
        break;
      }

      case "run_completed":
        setRunStatus("completed");
        setTokensSummary({
          in: event.tokens_in ?? 0,
          out: event.tokens_out ?? 0,
          cost: event.cost_usd ?? 0,
        });
        cleanup();
        if (event.document_id) {
          onComplete(event.document_id);
        }
        break;

      case "run_failed": {
        const runError = event.error || "Generation failed unexpectedly.";
        const isRateLimit =
          runError.toLowerCase().includes("rate limit") ||
          runError.includes("429");
        toast({
          title: isRateLimit ? "Rate limit — generation stopped" : "Generation failed",
          description: isRateLimit
            ? "AI rate limit exhausted. Wait a minute then retry the run."
            : runError.slice(0, 200),
          variant: "destructive",
        });
        setRunStatus("failed");
        cleanup();
        break;
      }
    }
  };

  const sortedPhases = [...phases].sort((a, b) => a.order - b.order);
  const doneCount = phases.filter((p) => p.status === "done").length;
  const totalPhases = Math.max(phases.length, totalPhasesFromServer);
  const progressPct = totalPhases > 0 ? Math.round((doneCount / totalPhases) * 100) : 0;

  const formatElapsed = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {runStatus === "running" || runStatus === "connecting" ? (
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
          ) : runStatus === "completed" ? (
            <CheckCircle className="h-4 w-4 text-green-600" />
          ) : (
            <XCircle className="h-4 w-4 text-red-600" />
          )}
          <span className="text-sm font-semibold text-gray-900">
            {runStatus === "connecting" && "Connecting..."}
            {runStatus === "running" && "Generating worksheet"}
            {runStatus === "completed" && "Generation complete"}
            {runStatus === "failed" && "Generation cancelled or failed"}
          </span>
        </div>

        <div className="flex items-center gap-3">
          {/* Cancel button — only while running */}
          {(runStatus === "running" || runStatus === "connecting") && (
            <button
              onClick={handleCancel}
              disabled={cancelling}
              className="flex items-center gap-1.5 text-xs font-medium text-red-600 hover:text-red-700 disabled:opacity-50 border border-red-200 rounded-md px-2.5 py-1 hover:bg-red-50 transition-colors"
            >
              {cancelling ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <StopCircle className="h-3.5 w-3.5" />
              )}
              {cancelling ? "Cancelling…" : "Cancel"}
            </button>
          )}

          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="h-3.5 w-3.5" />
            {formatElapsed(elapsedSeconds)}
          </div>
        </div>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-100 rounded-full h-2">
        <div
          className={`h-2 rounded-full transition-all duration-500 ${
            runStatus === "failed" ? "bg-red-500" : "bg-primary"
          }`}
          style={{ width: `${runStatus === "completed" ? 100 : progressPct}%` }}
        />
      </div>

      {/* Current phase */}
      {currentPhase && runStatus === "running" && (
        <p className="text-xs text-muted-foreground">
          {FIXED_PHASE_LABELS[currentPhase] || currentPhase}...
        </p>
      )}

      {/* Phase chips */}
      {sortedPhases.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {sortedPhases.map((phase) => (
            <div
              key={phase.name}
              className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border font-medium ${
                phase.status === "done"
                  ? "bg-green-50 text-green-700 border-green-200"
                  : phase.status === "running"
                  ? "bg-blue-50 text-blue-700 border-blue-200"
                  : phase.status === "failed"
                  ? "bg-red-50 text-red-700 border-red-200"
                  : "bg-gray-50 text-gray-600 border-gray-200"
              }`}
            >
              {phase.status === "done" && <CheckCircle className="h-3 w-3" />}
              {phase.status === "running" && <Loader2 className="h-3 w-3 animate-spin" />}
              {phase.status === "failed" && <XCircle className="h-3 w-3" />}
              {phase.status === "queued" && <Circle className="h-3 w-3" />}
              {phase.label}
            </div>
          ))}
        </div>
      )}

      {/* Cost summary on completion */}
      {runStatus === "completed" && tokensSummary && (
        <div className="bg-green-50 border border-green-200 rounded-md px-3 py-2 text-xs text-green-800">
          <span className="font-semibold">Done!</span> Tokens: {tokensSummary.in.toLocaleString()}{" "}
          in / {tokensSummary.out.toLocaleString()} out — Cost: $
          {tokensSummary.cost.toFixed(4)}
        </div>
      )}

      {runStatus === "failed" && (
        <div className="bg-red-50 border border-red-200 rounded-md px-3 py-2 text-xs text-red-700">
          Generation failed. Check phase status above and retry from the failed phase.
        </div>
      )}
    </div>
  );
}
