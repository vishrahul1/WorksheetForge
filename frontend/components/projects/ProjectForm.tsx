"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import type { ProjectCreatePayload } from "@/types";

interface Props {
  initialValues?: Partial<ProjectCreatePayload>;
  onSubmit: (data: ProjectCreatePayload) => Promise<void>;
  submitLabel?: string;
}

export function ProjectForm({ initialValues, onSubmit, submitLabel = "Save" }: Props) {
  const [name, setName] = useState(initialValues?.name || "");
  const [description, setDescription] = useState(initialValues?.description || "");
  const [subject, setSubject] = useState(initialValues?.subject || "");
  const [gradeLevel, setGradeLevel] = useState(initialValues?.grade_level || "");
  const [systemInstructions, setSystemInstructions] = useState(
    initialValues?.system_instructions || ""
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError("Project name is required.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await onSubmit({
        name: name.trim(),
        description: description.trim() || undefined,
        subject: subject.trim() || undefined,
        grade_level: gradeLevel.trim() || undefined,
        system_instructions: systemInstructions.trim() || undefined,
      });
    } catch (err: any) {
      setError(err.message || "An error occurred. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Project name <span className="text-red-500">*</span>
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          placeholder="e.g. JEE Physics — Mechanics"
          required
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent resize-none"
          placeholder="Optional description"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Subject</label>
          <input
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            placeholder="e.g. Physics"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Grade / Level</label>
          <input
            type="text"
            value={gradeLevel}
            onChange={(e) => setGradeLevel(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            placeholder="e.g. JEE Advanced"
          />
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          System instructions
        </label>
        <p className="text-xs text-muted-foreground mb-1.5">
          Instructions for the AI — topic focus, difficulty distribution, question style, etc.
        </p>
        <textarea
          value={systemInstructions}
          onChange={(e) => setSystemInstructions(e.target.value)}
          rows={6}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent resize-y"
          placeholder={`e.g. Generate a 30-question JEE Advanced worksheet on Newton's Laws.
- 10 MCQs (easy–medium), 10 MCQs (hard), 5 integer-type, 5 paragraph-based.
- Focus on application and multi-concept problems.
- All solutions must show step-by-step working with LaTeX.`}
        />
      </div>

      {error && (
        <div className="rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={loading}
          className="flex items-center gap-2 rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading && <Loader2 className="h-4 w-4 animate-spin" />}
          {loading ? "Saving..." : submitLabel}
        </button>
      </div>
    </form>
  );
}
