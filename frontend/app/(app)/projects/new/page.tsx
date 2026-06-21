"use client";

import { useRouter } from "next/navigation";
import { projectsApi } from "@/lib/api";
import { ProjectForm } from "@/components/projects/ProjectForm";
import type { ProjectCreatePayload } from "@/types";

export default function NewProjectPage() {
  const router = useRouter();

  const handleSubmit = async (data: ProjectCreatePayload) => {
    const project = await projectsApi.create(data);
    router.push(`/projects/${project.id}`);
  };

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-8">
        <button
          onClick={() => router.back()}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ← Back
        </button>
        <h1 className="text-2xl font-bold text-gray-900 mt-2">New Project</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Set up a worksheet generation project with source files and instructions.
        </p>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <ProjectForm onSubmit={handleSubmit} submitLabel="Create Project" />
      </div>
    </div>
  );
}
