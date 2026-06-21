"use client";

import { useCallback, useState } from "react";
import { Upload, Loader2, CheckCircle, AlertCircle } from "lucide-react";
import { filesApi } from "@/lib/api";

interface Props {
  projectId: string;
  onUploaded: () => void;
}

const ACCEPTED_TYPES = ".pdf,.docx,.doc,.txt,.md";
const MAX_SIZE_MB = 50;

export function FileUpload({ projectId, onUploaded }: Props) {
  const [dragging, setDragging] = useState(false);
  const [uploads, setUploads] = useState<
    { file: File; status: "uploading" | "done" | "error"; error?: string }[]
  >([]);

  const uploadFile = async (file: File) => {
    setUploads((prev) => [...prev, { file, status: "uploading" }]);

    try {
      if (file.size > MAX_SIZE_MB * 1024 * 1024) {
        throw new Error(`File exceeds ${MAX_SIZE_MB} MB limit`);
      }
      await filesApi.upload(projectId, file);
      setUploads((prev) =>
        prev.map((u) => (u.file === file ? { ...u, status: "done" } : u))
      );
      onUploaded();
    } catch (err: any) {
      setUploads((prev) =>
        prev.map((u) =>
          u.file === file ? { ...u, status: "error", error: err.message || "Upload failed" } : u
        )
      );
    }
  };

  const handleFiles = (files: FileList | null) => {
    if (!files) return;
    Array.from(files).forEach(uploadFile);
  };

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      handleFiles(e.dataTransfer.files);
    },
    [projectId]
  );

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  };

  const handleDragLeave = () => setDragging(false);

  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    handleFiles(e.target.files);
    e.target.value = ""; // reset
  };

  return (
    <div className="space-y-3">
      <label
        className={`flex flex-col items-center justify-center w-full border-2 border-dashed rounded-lg p-8 cursor-pointer transition-colors ${
          dragging
            ? "border-primary bg-primary/5"
            : "border-gray-300 hover:border-gray-400 hover:bg-gray-50"
        }`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        <Upload className="h-8 w-8 text-muted-foreground mb-2" />
        <p className="text-sm font-medium text-gray-700">
          Drop files here or <span className="text-primary">browse</span>
        </p>
        <p className="text-xs text-muted-foreground mt-1">
          PDF, DOCX, TXT, MD — up to {MAX_SIZE_MB} MB each
        </p>
        <input
          type="file"
          accept={ACCEPTED_TYPES}
          multiple
          onChange={handleInput}
          className="hidden"
        />
      </label>

      {uploads.length > 0 && (
        <ul className="space-y-1.5">
          {uploads.map((u, i) => (
            <li
              key={i}
              className="flex items-center gap-3 text-sm px-3 py-2 rounded-md bg-gray-50 border border-gray-200"
            >
              {u.status === "uploading" && (
                <Loader2 className="h-4 w-4 animate-spin text-primary shrink-0" />
              )}
              {u.status === "done" && (
                <CheckCircle className="h-4 w-4 text-green-600 shrink-0" />
              )}
              {u.status === "error" && (
                <AlertCircle className="h-4 w-4 text-red-600 shrink-0" />
              )}
              <span className="flex-1 truncate text-gray-700">{u.file.name}</span>
              {u.status === "error" && u.error && (
                <span className="text-xs text-red-600 shrink-0">{u.error}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
