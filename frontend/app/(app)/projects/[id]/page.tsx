"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { documentsApi, filesApi, projectsApi } from "@/lib/api";
import { Loader2, Settings } from "lucide-react";
import { FileUpload } from "@/components/files/FileUpload";
import { GenerateButton } from "@/components/generation/GenerateButton";
import { PhaseProgress } from "@/components/generation/PhaseProgress";
import { GenerationPreview } from "@/components/generation/GenerationPreview";
import { ChatPanel } from "@/components/chat/ChatPanel";
import type { Document, ProjectFile, Run } from "@/types";
import { formatDistanceToNow } from "@/lib/utils";

type Tab = "files" | "generate" | "history" | "chat";

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<Tab>("files");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);

  const { data: project, isLoading: projectLoading } = useQuery({
    queryKey: ["project", id],
    queryFn: () => projectsApi.get(id),
  });

  const { data: filesData, isLoading: filesLoading } = useQuery({
    queryKey: ["files", id],
    queryFn: () => filesApi.list(id),
  });

  const { data: runsData } = useQuery({
    queryKey: ["runs", id],
    queryFn: async () => {
      // Fetch all runs via multiple calls if needed
      // For now, rely on run IDs stored in project runs
      return [] as Run[];
    },
    enabled: activeTab === "history" || activeTab === "generate",
  });

  const handleFileDeleted = (fileId: string) => {
    queryClient.invalidateQueries({ queryKey: ["files", id] });
  };

  const handleGenerateStart = (runId: string) => {
    setActiveRunId(runId);
    setActiveTab("generate");
  };

  const handleRunComplete = (documentId: string) => {
    // Invalidate history cache so new document shows in History tab
    queryClient.invalidateQueries({ queryKey: ["documents", id] });
    // Stay on Generate tab — preview renders here after completion
  };

  if (projectLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="text-center py-16">
        <p className="text-muted-foreground">Project not found.</p>
      </div>
    );
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: "files", label: "Files" },
    { key: "generate", label: "Generate" },
    { key: "history", label: "History" },
    { key: "chat", label: "Chat" },
  ];

  return (
    <div>
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <button
            onClick={() => router.push("/projects")}
            className="text-sm text-muted-foreground hover:text-foreground mb-1"
          >
            ← Projects
          </button>
          <h1 className="text-2xl font-bold text-gray-900">{project.name}</h1>
          {project.description && (
            <p className="text-sm text-muted-foreground mt-1">{project.description}</p>
          )}
          {project.subject && (
            <span className="inline-block mt-2 text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded px-2 py-0.5">
              {project.subject}
              {project.grade_level ? ` · ${project.grade_level}` : ""}
            </span>
          )}
        </div>
        <button
          onClick={() => router.push(`/projects/${id}/edit`)}
          className="flex items-center gap-1.5 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
        >
          <Settings className="h-4 w-4" />
          Edit
        </button>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      {activeTab === "files" && (
        <FilesTab
          projectId={id}
          files={filesData?.files || []}
          loading={filesLoading}
          onFilesChanged={() => queryClient.invalidateQueries({ queryKey: ["files", id] })}
        />
      )}

      {activeTab === "generate" && (
        <GenerateTab
          projectId={id}
          files={filesData?.files || []}
          activeRunId={activeRunId}
          onStart={handleGenerateStart}
          onComplete={handleRunComplete}
        />
      )}

      {activeTab === "history" && (
        <HistoryTab projectId={id} />
      )}

      {activeTab === "chat" && (
        <ChatPanel projectId={id} />
      )}
    </div>
  );
}

// ─── FilesTab ─────────────────────────────────────────────────────────────────

function FilesTab({
  projectId,
  files,
  loading,
  onFilesChanged,
}: {
  projectId: string;
  files: ProjectFile[];
  loading: boolean;
  onFilesChanged: () => void;
}) {
  const handleDelete = async (fileId: string) => {
    await filesApi.delete(projectId, fileId);
    onFilesChanged();
  };

  return (
    <div className="space-y-6">
      <FileUpload projectId={projectId} onUploaded={onFilesChanged} />

      {loading && (
        <div className="flex items-center gap-2 text-muted-foreground text-sm">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading files...
        </div>
      )}

      {!loading && files.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No source files yet. Upload PDFs or DOCX files to get started.
        </p>
      )}

      {files.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-gray-700">Source files ({files.length})</h3>
          <ul className="divide-y divide-gray-100 border border-gray-200 rounded-lg overflow-hidden">
            {files.map((file) => (
              <li
                key={file.id}
                className="flex items-center justify-between px-4 py-3 bg-white hover:bg-gray-50"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">{file.filename}</p>
                  <p className="text-xs text-muted-foreground">
                    {(file.size_bytes / 1024).toFixed(1)} KB · {file.mime_type}
                  </p>
                </div>
                <button
                  onClick={() => handleDelete(file.id)}
                  className="ml-4 text-sm text-red-600 hover:text-red-700 shrink-0"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ─── GenerateTab ──────────────────────────────────────────────────────────────

function GenerateTab({
  projectId,
  files,
  activeRunId,
  onStart,
  onComplete,
}: {
  projectId: string;
  files: ProjectFile[];
  activeRunId: string | null;
  onStart: (runId: string) => void;
  onComplete: (documentId: string) => void;
}) {
  const [completedRunId, setCompletedRunId] = useState<string | null>(null);
  const [completedDocId, setCompletedDocId] = useState<string | null>(null);

  const handleComplete = (documentId: string) => {
    // Capture activeRunId immediately before any parent state changes
    const runId = activeRunId;
    setCompletedRunId(runId);
    setCompletedDocId(documentId);
    onComplete(documentId);
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <GenerateButton
        projectId={projectId}
        files={files}
        onRunStarted={(runId) => {
          // Clear previous preview when starting a new run
          setCompletedRunId(null);
          setCompletedDocId(null);
          onStart(runId);
        }}
      />

      {activeRunId && (
        <PhaseProgress
          runId={activeRunId}
          onComplete={handleComplete}
        />
      )}

      {/* Preview + Log — shown after generation completes */}
      {completedRunId && completedDocId && (
        <GenerationPreview
          runId={completedRunId}
          documentId={completedDocId}
        />
      )}
    </div>
  );
}

// ─── HistoryTab ───────────────────────────────────────────────────────────────

function HistoryTab({ projectId }: { projectId: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: documents, isLoading } = useQuery({
    queryKey: ["documents", projectId],
    queryFn: () => projectsApi.listDocuments(projectId),
    refetchInterval: 60_000,
  });

  const handleDelete = async (docId: string) => {
    await documentsApi.delete(docId);
    queryClient.invalidateQueries({ queryKey: ["documents", projectId] });
  };

  const handleDownload = async (docId: string) => {
    const data = await documentsApi.getDownloadUrl(docId);
    window.open(data.download_url, "_blank");
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground text-sm">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading history...
      </div>
    );
  }

  if (!documents || documents.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No generated worksheets yet. Run generation from the Generate tab.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {documents.map((doc) => (
        <div
          key={doc.id}
          className="bg-white border border-gray-200 rounded-lg px-4 py-4 flex items-center justify-between gap-4"
        >
          <div className="flex-1 min-w-0">
            <p className="font-medium text-sm text-gray-900 truncate">{doc.title}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {doc.is_expired ? (
                <span className="text-red-600 font-medium">Expired</span>
              ) : (
                <span className="text-amber-600">
                  Expires in {formatExpiryTime(doc.time_remaining_seconds)}
                </span>
              )}
              {" · "}v{doc.current_version}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => router.push(`/projects/${projectId}/documents/${doc.id}`)}
              className="text-sm text-blue-600 hover:text-blue-700"
            >
              Edit
            </button>
            <button
              onClick={() => handleDownload(doc.id)}
              disabled={doc.is_expired}
              className="text-sm text-primary hover:text-primary/80 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Download
            </button>
            <button
              onClick={() => handleDelete(doc.id)}
              className="text-sm text-red-600 hover:text-red-700"
            >
              Delete
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

function formatExpiryTime(seconds: number): string {
  if (seconds <= 0) return "expired";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}
