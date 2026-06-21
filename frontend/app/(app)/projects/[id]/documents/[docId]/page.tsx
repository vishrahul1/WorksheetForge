"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { documentsApi } from "@/lib/api";
import { Loader2 } from "lucide-react";
import { DocEditor } from "@/components/editor/DocEditor";

export default function DocumentEditorPage() {
  const { id: projectId, docId } = useParams<{ id: string; docId: string }>();
  const router = useRouter();

  const { data: document, isLoading } = useQuery({
    queryKey: ["document", docId],
    queryFn: () => documentsApi.get(docId),
    refetchInterval: 30_000, // refresh TTL countdown every 30s
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!document) {
    return <p className="text-muted-foreground">Document not found.</p>;
  }

  return (
    <div>
      <div className="mb-4">
        <button
          onClick={() => router.push(`/projects/${projectId}`)}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ← Back to project
        </button>
      </div>

      <DocEditor document={document} projectId={projectId} />
    </div>
  );
}
