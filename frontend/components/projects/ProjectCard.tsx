import type { ProjectListItem } from "@/types";
import { formatDistanceToNow } from "@/lib/utils";
import { CheckCircle, Clock, XCircle, AlertCircle, FileText } from "lucide-react";

interface Props {
  project: ProjectListItem;
  onClick: () => void;
}

function RunStatusBadge({ status }: { status: string | null }) {
  if (!status) return null;

  const config: Record<string, { icon: React.ReactNode; label: string; className: string }> = {
    completed: {
      icon: <CheckCircle className="h-3 w-3" />,
      label: "Completed",
      className: "bg-green-50 text-green-700 border-green-200",
    },
    running: {
      icon: <Clock className="h-3 w-3 animate-spin" />,
      label: "Running",
      className: "bg-blue-50 text-blue-700 border-blue-200",
    },
    queued: {
      icon: <Clock className="h-3 w-3" />,
      label: "Queued",
      className: "bg-gray-50 text-gray-700 border-gray-200",
    },
    failed: {
      icon: <XCircle className="h-3 w-3" />,
      label: "Failed",
      className: "bg-red-50 text-red-700 border-red-200",
    },
    cancelled: {
      icon: <AlertCircle className="h-3 w-3" />,
      label: "Cancelled",
      className: "bg-yellow-50 text-yellow-700 border-yellow-200",
    },
  };

  const c = config[status];
  if (!c) return null;

  return (
    <span
      className={`inline-flex items-center gap-1 text-xs border rounded-full px-2 py-0.5 font-medium ${c.className}`}
    >
      {c.icon}
      {c.label}
    </span>
  );
}

export function ProjectCard({ project, onClick }: Props) {
  return (
    <div
      onClick={onClick}
      className="bg-white border border-gray-200 rounded-lg p-5 cursor-pointer hover:border-primary/50 hover:shadow-sm transition-all group"
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-gray-900 truncate group-hover:text-primary transition-colors">
            {project.name}
          </h3>
          {project.description && (
            <p className="text-sm text-muted-foreground mt-0.5 line-clamp-2">
              {project.description}
            </p>
          )}
        </div>
        <FileText className="h-5 w-5 text-muted-foreground shrink-0 mt-0.5" />
      </div>

      <div className="flex items-center justify-between mt-4">
        <div className="flex items-center gap-2">
          {project.subject && (
            <span className="text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded px-1.5 py-0.5">
              {project.subject}
            </span>
          )}
          {project.grade_level && (
            <span className="text-xs bg-purple-50 text-purple-700 border border-purple-200 rounded px-1.5 py-0.5">
              {project.grade_level}
            </span>
          )}
        </div>
        <RunStatusBadge status={project.last_run_status} />
      </div>

      <p className="text-xs text-muted-foreground mt-3">
        Updated {formatDistanceToNow(project.updated_at)}
      </p>
    </div>
  );
}
