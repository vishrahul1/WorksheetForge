"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useEditor, EditorContent, BubbleMenu } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { documentsApi } from "@/lib/api";
import type { Document } from "@/types";
import { formatExpiryTime } from "@/lib/utils";
import {
  Bold,
  Italic,
  Heading2,
  Heading3,
  List,
  ListOrdered,
  Download,
  Save,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import { VersionHistory } from "./VersionHistory";

interface Props {
  document: Document;
  projectId: string;
}

export function DocEditor({ document, projectId }: Props) {
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saved" | "error">("idle");
  const [downloading, setDownloading] = useState(false);
  const [timeRemaining, setTimeRemaining] = useState(document.time_remaining_seconds);
  const [showVersions, setShowVersions] = useState(false);
  const autoSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Countdown timer
  useEffect(() => {
    if (timeRemaining <= 0) return;
    const interval = setInterval(() => {
      setTimeRemaining((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const [contentLoading, setContentLoading] = useState(true);
  const [contentError, setContentError] = useState<string | null>(null);

  const editor = useEditor({
    extensions: [StarterKit],
    content: "",
    onUpdate: ({ editor }) => {
      if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);
      setSaveStatus("idle");
      autoSaveTimerRef.current = setTimeout(() => {
        handleSave(editor.getHTML());
      }, 3000);
    },
  });

  // Load document content from backend on mount
  useEffect(() => {
    if (!editor) return;
    setContentLoading(true);
    documentsApi
      .getContent(document.id)
      .then(({ html }) => {
        editor.commands.setContent(html || "<p>Empty document.</p>");
        setContentLoading(false);
      })
      .catch(() => {
        setContentError("Failed to load document content.");
        setContentLoading(false);
      });
  }, [editor, document.id]);

  const handleSave = useCallback(
    async (html: string) => {
      if (!editor || timeRemaining <= 0) return;
      setSaving(true);
      try {
        await documentsApi.save(document.id, html);
        setSaveStatus("saved");
        setTimeout(() => setSaveStatus("idle"), 2000);
      } catch {
        setSaveStatus("error");
      } finally {
        setSaving(false);
      }
    },
    [document.id, editor, timeRemaining]
  );

  const handleManualSave = () => {
    if (!editor) return;
    handleSave(editor.getHTML());
  };

  const handleDownload = async () => {
    if (timeRemaining <= 0) return;
    setDownloading(true);
    try {
      const data = await documentsApi.getDownloadUrl(document.id);
      window.open(data.download_url, "_blank");
    } catch (err: any) {
      alert(err.message || "Download failed");
    } finally {
      setDownloading(false);
    }
  };

  const isExpired = timeRemaining <= 0;
  const isWarning = timeRemaining > 0 && timeRemaining < 1800; // < 30 min

  return (
    <div className="flex flex-col h-full">
      {/* Expiry banner — the most important UI element for the 2-hour ephemeral feature */}
      {isExpired ? (
        <div className="bg-red-600 text-white text-sm px-4 py-3 flex items-center gap-2 rounded-t-lg">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span className="font-semibold">
            This document has expired and can no longer be downloaded.
          </span>
        </div>
      ) : (
        <div
          className={`text-sm px-4 py-2.5 flex items-center justify-between rounded-t-lg border-b ${
            isWarning
              ? "bg-amber-50 border-amber-200 text-amber-800"
              : "bg-blue-50 border-blue-200 text-blue-800"
          }`}
        >
          <div className="flex items-center gap-2">
            {isWarning && <AlertTriangle className="h-4 w-4 shrink-0" />}
            <span>
              This document expires in{" "}
              <span className="font-bold">{formatExpiryTime(timeRemaining)}</span> — download
              before it&apos;s deleted.
            </span>
          </div>
          <button
            onClick={handleDownload}
            disabled={downloading || isExpired}
            className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-md transition-colors ${
              isWarning
                ? "bg-amber-600 text-white hover:bg-amber-700"
                : "bg-blue-600 text-white hover:bg-blue-700"
            } disabled:opacity-50`}
          >
            {downloading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
            Download
          </button>
        </div>
      )}

      {/* Document title + toolbar */}
      <div className="bg-white border-b border-gray-200 px-4 py-2 flex items-center justify-between gap-4">
        <h2 className="font-semibold text-gray-900 truncate text-sm">{document.title}</h2>

        <div className="flex items-center gap-2">
          {/* Toolbar */}
          {editor && (
            <div className="flex items-center gap-0.5 border border-gray-200 rounded-md p-0.5">
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleBold().run()}
                active={editor.isActive("bold")}
                title="Bold"
              >
                <Bold className="h-3.5 w-3.5" />
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleItalic().run()}
                active={editor.isActive("italic")}
                title="Italic"
              >
                <Italic className="h-3.5 w-3.5" />
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
                active={editor.isActive("heading", { level: 2 })}
                title="Heading 2"
              >
                <Heading2 className="h-3.5 w-3.5" />
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
                active={editor.isActive("heading", { level: 3 })}
                title="Heading 3"
              >
                <Heading3 className="h-3.5 w-3.5" />
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleBulletList().run()}
                active={editor.isActive("bulletList")}
                title="Bullet list"
              >
                <List className="h-3.5 w-3.5" />
              </ToolbarButton>
              <ToolbarButton
                onClick={() => editor.chain().focus().toggleOrderedList().run()}
                active={editor.isActive("orderedList")}
                title="Ordered list"
              >
                <ListOrdered className="h-3.5 w-3.5" />
              </ToolbarButton>
            </div>
          )}

          <button
            onClick={() => setShowVersions((v) => !v)}
            className="text-xs text-muted-foreground hover:text-foreground border border-gray-200 rounded-md px-2.5 py-1.5 transition-colors"
          >
            v{document.current_version}
          </button>

          <button
            onClick={handleManualSave}
            disabled={saving || isExpired}
            className="flex items-center gap-1.5 text-xs font-medium border border-gray-300 rounded-md px-3 py-1.5 text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
            {saving ? "Saving..." : saveStatus === "saved" ? "Saved" : "Save"}
          </button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Editor */}
        <div className="flex-1 overflow-y-auto bg-white relative">
          {contentLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-white z-10">
              <div className="flex items-center gap-2 text-muted-foreground text-sm">
                <Loader2 className="h-5 w-5 animate-spin" />
                Loading document...
              </div>
            </div>
          )}
          {contentError && (
            <div className="m-4 rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
              {contentError}
            </div>
          )}
          {editor && !contentLoading && (
            <BubbleMenu editor={editor} tippyOptions={{ duration: 100 }}>
              <div className="flex items-center gap-0.5 bg-white border border-gray-200 rounded-md shadow-lg p-1">
                <ToolbarButton
                  onClick={() => editor.chain().focus().toggleBold().run()}
                  active={editor.isActive("bold")}
                  title="Bold"
                >
                  <Bold className="h-3.5 w-3.5" />
                </ToolbarButton>
                <ToolbarButton
                  onClick={() => editor.chain().focus().toggleItalic().run()}
                  active={editor.isActive("italic")}
                  title="Italic"
                >
                  <Italic className="h-3.5 w-3.5" />
                </ToolbarButton>
              </div>
            </BubbleMenu>
          )}
          <EditorContent
            editor={editor}
            className="prose prose-sm max-w-none min-h-screen"
          />
        </div>

        {/* Version history sidebar */}
        {showVersions && (
          <div className="w-72 border-l border-gray-200 bg-gray-50 overflow-y-auto">
            <VersionHistory documentId={document.id} currentVersion={document.current_version} />
          </div>
        )}
      </div>
    </div>
  );
}

function ToolbarButton({
  children,
  onClick,
  active,
  title,
}: {
  children: React.ReactNode;
  onClick: () => void;
  active?: boolean;
  title?: string;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={`p-1.5 rounded transition-colors ${
        active ? "bg-primary text-primary-foreground" : "text-gray-600 hover:bg-gray-100"
      }`}
    >
      {children}
    </button>
  );
}
