"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { projectsApi } from "@/lib/api";
import { ProjectForm } from "@/components/projects/ProjectForm";
import { Loader2 } from "lucide-react";
import type { ProjectUpdatePayload } from "@/types";

export default function EditProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: project, isLoading } = useQuery({
    queryKey: ["project", id],
    queryFn: () => projectsApi.get(id),
  });

  const handleSubmit = async (data: ProjectUpdatePayload) => {
    await projectsApi.update(id, data);
    queryClient.invalidateQueries({ queryKey: ["project", id] });
    router.push(`/projects/${id}`);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!project) {
    return <p className="text-muted-foreground">Project not found.</p>;
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-8">
        <button
          onClick={() => router.back()}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ← Back
        </button>
        <h1 className="text-2xl font-bold text-gray-900 mt-2">Edit Project</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Update project settings and generation instructions.
        </p>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <ProjectForm
          initialValues={project}
          onSubmit={handleSubmit}
          submitLabel="Save Changes"
        />
      </div>
    </div>
  );
}
