// ─── Auth ─────────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  full_name: string | null;
}

// ─── Projects ─────────────────────────────────────────────────────────────────

export interface Project {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  system_instructions: string | null;
  subject: string | null;
  grade_level: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectListItem extends Project {
  last_run_status: string | null;
}

export interface ProjectCreatePayload {
  name: string;
  description?: string;
  system_instructions?: string;
  subject?: string;
  grade_level?: string;
}

export interface ProjectUpdatePayload {
  name?: string;
  description?: string;
  system_instructions?: string;
  subject?: string;
  grade_level?: string;
}

// ─── Files ────────────────────────────────────────────────────────────────────

export interface ProjectFile {
  id: string;
  project_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  storage_path: string;
  created_at: string;
}

// ─── Runs ─────────────────────────────────────────────────────────────────────

export type RunStatus = "queued" | "running" | "completed" | "failed" | "cancelled";
export type PhaseStatus = "queued" | "running" | "done" | "failed";

export interface RunPhase {
  id: string;
  run_id: string;
  phase_name: string;
  phase_order: number;
  status: PhaseStatus;
  output: string | null;
  prompt_sent: string | null;
  tokens_in: number;
  tokens_out: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface Run {
  id: string;
  project_id: string;
  status: RunStatus;
  selected_file_ids: string[] | null;
  total_tokens_in: number;
  total_tokens_out: number;
  estimated_cost_usd: number | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  phases: RunPhase[];
}

// ─── Documents ────────────────────────────────────────────────────────────────

export interface DocumentVersion {
  id: string;
  document_id: string;
  version_number: number;
  storage_path: string;
  size_bytes: number | null;
  created_at: string;
}

export interface Document {
  id: string;
  run_id: string;
  project_id: string;
  title: string;
  current_version: number;
  expires_at: string;
  created_at: string;
  updated_at: string;
  versions: DocumentVersion[];
  time_remaining_seconds: number;
  is_expired: boolean;
}

export interface DocumentDownloadResponse {
  download_url: string;
  filename: string;
  expires_at: string;
  time_remaining_seconds: number;
}

// ─── Chat ─────────────────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  project_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

// ─── SSE Events ───────────────────────────────────────────────────────────────

export type SSEEventType =
  | "connected"
  | "run_started"
  | "phase_started"
  | "phase_completed"
  | "phase_failed"
  | "assembling_docx"
  | "run_completed"
  | "run_failed";

export interface SSEEvent {
  type: SSEEventType;
  run_id: string;
  phase?: string;
  phase_order?: number;
  total_phases?: number;
  tokens_in?: number;
  tokens_out?: number;
  document_id?: string;
  expires_at?: string;
  cost_usd?: number;
  error?: string;
}
