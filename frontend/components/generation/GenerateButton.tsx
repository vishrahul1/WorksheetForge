"use client";

import { useState } from "react";
import { runsApi } from "@/lib/api";
import { Loader2, Zap, ChevronDown } from "lucide-react";
import type { ProjectFile } from "@/types";

interface Props {
  projectId: string;
  files: ProjectFile[];
  onRunStarted: (runId: string) => void;
}

const PROVIDERS = {
  anthropic: {
    label: "Claude (Anthropic)",
    icon: "🤖",
    models: [
      { id: "claude-opus-4-5",   label: "Claude Opus 4.5",   badge: "Best quality", cost: "$15 / 1M tokens" },
      { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6", badge: "Balanced",      cost: "$3 / 1M tokens" },
      { id: "claude-haiku-4-5",  label: "Claude Haiku 4.5",  badge: "Fastest",       cost: "$0.80 / 1M tokens" },
    ],
  },
  gemini: {
    label: "Gemini (Google)",
    icon: "✨",
    models: [
      { id: "gemini-2.0-flash-lite", label: "Gemini 2.0 Flash Lite", badge: "Fast & cheap",  cost: "$0.075 / 1M tokens" },
      { id: "gemini-2.0-flash",      label: "Gemini 2.0 Flash",      badge: "Balanced",      cost: "$0.10 / 1M tokens"  },
      { id: "gemini-2.5-flash",      label: "Gemini 2.5 Flash",      badge: "Best quality",  cost: "$0.15 / 1M tokens"  },
    ],
  },
} as const;

type ProviderId = keyof typeof PROVIDERS;

// Smart default parallel count per provider
const DEFAULT_PARALLEL: Record<ProviderId, number> = {
  anthropic: 1,
  gemini: 3,
};

export function GenerateButton({ projectId, files, onRunStarted }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [provider, setProvider] = useState<ProviderId>("anthropic");
  const [model, setModel] = useState(PROVIDERS.anthropic.models[0].id);
  const [modelOpen, setModelOpen] = useState(false);
  const [parallelSections, setParallelSections] = useState(1);

  const toggleFile = (fileId: string) => {
    setSelectedFileIds((prev) =>
      prev.includes(fileId) ? prev.filter((id) => id !== fileId) : [...prev, fileId]
    );
  };

  const handleProviderChange = (p: ProviderId) => {
    setProvider(p);
    setModel(PROVIDERS[p].models[0].id);
    setParallelSections(DEFAULT_PARALLEL[p]);
  };

  const selectedModel = PROVIDERS[provider].models.find((m) => m.id === model)!;

  const handleGenerate = async () => {
    setError(null);
    setLoading(true);
    try {
      const run = await runsApi.create(
        projectId,
        selectedFileIds.length > 0 ? selectedFileIds : undefined,
        provider,
        model,
        parallelSections,
      );
      onRunStarted(run.id);
    } catch (err: any) {
      setError(err.message || "Failed to start generation. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* File selection */}
      {files.length > 0 && (
        <div>
          <p className="text-sm font-medium text-gray-700 mb-2">
            Source files{" "}
            <span className="text-muted-foreground font-normal">(all used if none selected)</span>
          </p>
          <ul className="space-y-1.5">
            {files.map((file) => (
              <li key={file.id}>
                <label className="flex items-center gap-3 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={selectedFileIds.includes(file.id)}
                    onChange={() => toggleFile(file.id)}
                    className="rounded border-gray-300 text-primary"
                  />
                  <span className="text-sm text-gray-700 group-hover:text-gray-900">{file.filename}</span>
                  <span className="text-xs text-muted-foreground ml-auto">
                    {(file.size_bytes / 1024).toFixed(1)} KB
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </div>
      )}

      {files.length === 0 && (
        <div className="rounded-md bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
          Upload source files first before generating a worksheet.
        </div>
      )}

      {/* Provider selector */}
      <div>
        <p className="text-sm font-medium text-gray-700 mb-2">AI Provider</p>
        <div className="flex gap-2">
          {(Object.entries(PROVIDERS) as [ProviderId, typeof PROVIDERS[ProviderId]][]).map(
            ([id, p]) => (
              <button
                key={id}
                onClick={() => handleProviderChange(id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition-colors ${
                  provider === id
                    ? "border-primary bg-primary/5 text-primary"
                    : "border-gray-200 text-gray-600 hover:border-gray-300"
                }`}
              >
                <span>{p.icon}</span>
                {p.label}
              </button>
            )
          )}
        </div>
      </div>

      {/* Model selector */}
      <div>
        <p className="text-sm font-medium text-gray-700 mb-2">Model</p>
        <div className="relative">
          <button
            onClick={() => setModelOpen((o) => !o)}
            className="w-full flex items-center justify-between gap-3 px-4 py-2.5 rounded-lg border border-gray-200 bg-white hover:border-gray-300 transition-colors"
          >
            <div className="flex items-center gap-3 min-w-0">
              <span className="text-sm font-medium text-gray-900">{selectedModel.label}</span>
              <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                {selectedModel.badge}
              </span>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <span className="text-xs text-muted-foreground">{selectedModel.cost}</span>
              <ChevronDown className={`h-4 w-4 text-gray-400 transition-transform ${modelOpen ? "rotate-180" : ""}`} />
            </div>
          </button>

          {modelOpen && (
            <div className="absolute z-10 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg overflow-hidden">
              {PROVIDERS[provider].models.map((m) => (
                <button
                  key={m.id}
                  onClick={() => { setModel(m.id); setModelOpen(false); }}
                  className={`w-full flex items-center justify-between px-4 py-2.5 hover:bg-gray-50 transition-colors ${
                    model === m.id ? "bg-primary/5" : ""
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span className={`text-sm font-medium ${model === m.id ? "text-primary" : "text-gray-900"}`}>
                      {m.label}
                    </span>
                    <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                      {m.badge}
                    </span>
                  </div>
                  <span className="text-xs text-muted-foreground">{m.cost}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Parallel sections */}
      <div>
        <p className="text-sm font-medium text-gray-700 mb-2">
          Sections per batch
          <span className="ml-2 text-xs font-normal text-muted-foreground">
            — how many sections generate simultaneously
          </span>
        </p>
        <div className="flex gap-2">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              onClick={() => setParallelSections(n)}
              className={`w-10 h-10 rounded-lg border text-sm font-medium transition-colors ${
                parallelSections === n
                  ? "border-primary bg-primary/5 text-primary"
                  : "border-gray-200 text-gray-600 hover:border-gray-300"
              }`}
            >
              {n}
            </button>
          ))}
        </div>
        {provider === "anthropic" && parallelSections > 1 && (
          <p className="text-xs text-amber-600 mt-1.5">
            ⚠ Anthropic Tier-1 accounts may hit rate limits with parallel &gt; 1. Use Gemini for best parallel performance.
          </p>
        )}
      </div>

      {error && (
        <div className="rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <button
        onClick={handleGenerate}
        disabled={loading || files.length === 0}
        className="flex items-center gap-2 rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
        {loading ? "Starting..." : `Generate with ${selectedModel.label}`}
      </button>
    </div>
  );
}
