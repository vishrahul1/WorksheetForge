import { getSession } from "next-auth/react";
import { toast } from "@/components/ui/toaster";
import type {
  ChatMessage,
  Document,
  DocumentDownloadResponse,
  DocumentVersion,
  Project,
  ProjectCreatePayload,
  ProjectFile,
  ProjectListItem,
  ProjectUpdatePayload,
  Run,
} from "@/types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function getAuthHeader(): Promise<Record<string, string>> {
  const session = await getSession();
  if (!session?.accessToken) return {};
  return { Authorization: `Bearer ${session.accessToken}` };
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  isFormData?: boolean
): Promise<T> {
  const authHeader = await getAuthHeader();
  const headers: Record<string, string> = {
    ...authHeader,
  };

  let bodyPayload: BodyInit | undefined;
  if (body && !isFormData) {
    headers["Content-Type"] = "application/json";
    bodyPayload = JSON.stringify(body);
  } else if (body instanceof FormData) {
    bodyPayload = body;
  }

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: bodyPayload,
    });
  } catch (networkErr) {
    const msg =
      `Cannot connect to the backend at ${BASE_URL}. ` +
      "Make sure Docker is running.";
    toast({ title: "Connection failed", description: msg, variant: "destructive" });
    throw new ApiError(0, msg);
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      detail = err.detail || detail;
    } catch {}

    // Show specific toast based on status code
    if (res.status === 429) {
      toast({
        title: "Rate limit reached",
        description: "The AI provider has hit its rate limit. The system will retry automatically.",
        variant: "destructive",
      });
    } else if (res.status === 410) {
      toast({
        title: "Document expired",
        description: "This document has expired and is no longer available.",
        variant: "destructive",
      });
    } else if (res.status === 401) {
      toast({
        title: "Session expired",
        description: "Please sign in again.",
        variant: "destructive",
      });
    } else if (res.status >= 500) {
      toast({
        title: "Server error",
        description: detail,
        variant: "destructive",
      });
    }

    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export const authApi = {
  login: (email: string, password: string) =>
    request<{ access_token: string }>("POST", "/auth/login", { email, password }),
  register: (email: string, password: string, full_name?: string) =>
    request<{ access_token: string }>("POST", "/auth/register", { email, password, full_name }),
  me: () => request<{ id: string; email: string; full_name: string | null }>("GET", "/auth/me"),
};

// ─── Projects ─────────────────────────────────────────────────────────────────

export const projectsApi = {
  list: () => request<ProjectListItem[]>("GET", "/projects"),
  create: (payload: ProjectCreatePayload) =>
    request<Project>("POST", "/projects", payload),
  get: (id: string) => request<Project>("GET", `/projects/${id}`),
  update: (id: string, payload: ProjectUpdatePayload) =>
    request<Project>("PATCH", `/projects/${id}`, payload),
  delete: (id: string) => request<void>("DELETE", `/projects/${id}`),
  listDocuments: (projectId: string) =>
    request<Document[]>("GET", `/projects/${projectId}/documents`),
};

// ─── Files ────────────────────────────────────────────────────────────────────

export const filesApi = {
  list: (projectId: string) =>
    request<{ files: ProjectFile[]; total: number }>("GET", `/projects/${projectId}/files`),
  upload: async (projectId: string, file: File): Promise<ProjectFile> => {
    const formData = new FormData();
    formData.append("file", file);
    return request<ProjectFile>("POST", `/projects/${projectId}/files`, formData, true);
  },
  delete: (projectId: string, fileId: string) =>
    request<void>("DELETE", `/projects/${projectId}/files/${fileId}`),
};

// ─── Runs ─────────────────────────────────────────────────────────────────────

export const runsApi = {
  create: (
    projectId: string,
    selectedFileIds?: string[],
    llmProvider?: string,
    llmModel?: string,
    parallelSections?: number,
  ) =>
    request<Run>("POST", `/projects/${projectId}/runs`, {
      selected_file_ids: selectedFileIds,
      llm_provider: llmProvider,
      llm_model: llmModel,
      parallel_sections: parallelSections ?? 1,
    }),
  get: (runId: string) => request<Run>("GET", `/runs/${runId}`),
  getPhases: (runId: string) => request<RunPhase[]>("GET", `/runs/${runId}/phases`),
  cancel: (runId: string) => request<{ status: string }>("POST", `/runs/${runId}/cancel`),
  retryPhase: (runId: string, phaseName: string) =>
    request<{ status: string }>("POST", `/runs/${runId}/phases/${phaseName}/retry`),
};

// ─── Documents ────────────────────────────────────────────────────────────────

export const documentsApi = {
  get: (docId: string) => request<Document>("GET", `/documents/${docId}`),
  getContent: (docId: string) =>
    request<{ html: string; title: string }>("GET", `/documents/${docId}/content`),
  getDownloadUrl: (docId: string) =>
    request<DocumentDownloadResponse>("GET", `/documents/${docId}/download`),
  save: (docId: string, contentHtml: string, title?: string) =>
    request<Document>("POST", `/documents/${docId}/save`, {
      content_html: contentHtml,
      title,
    }),
  listVersions: (docId: string) =>
    request<DocumentVersion[]>("GET", `/documents/${docId}/versions`),
  delete: (docId: string) => request<void>("DELETE", `/documents/${docId}`),
};

// ─── Chat ─────────────────────────────────────────────────────────────────────

export const chatApi = {
  history: (projectId: string) =>
    request<ChatMessage[]>("GET", `/projects/${projectId}/chat`),
  send: (projectId: string, content: string) =>
    request<ChatMessage>("POST", `/projects/${projectId}/chat`, { content }),
};

export { ApiError };
export default { authApi, projectsApi, filesApi, runsApi, documentsApi, chatApi };
