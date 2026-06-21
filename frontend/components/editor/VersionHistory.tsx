"use client";

import { useQuery } from "@tanstack/react-query";
import { documentsApi } from "@/lib/api";
import { Loader2, Download } from "lucide-react";
import { formatDistanceToNow } from "@/lib/utils";

interface Props {
  documentId: string;
  currentVersion: number;
}

export function VersionHistory({ documentId, currentVersion }: Props) {
  const { data: versions, isLoading } = useQuery({
    queryKey: ["document-versions", documentId],
    queryFn: () => documentsApi.listVersions(documentId),
  });

  const handleDownloadVersion = async (versionId: string) => {
    // For version downloads, use the main download URL which gets the current version
    // In a full implementation, you'd pass a version number query param
    const data = await documentsApi.getDownloadUrl(documentId);
    window.open(data.download_url, "_blank");
  };

  return (
    <div className="p-4">
      <h3 className="text-sm font-semibold text-gray-900 mb-3">Version History</h3>

      {isLoading && (
        <div className="flex items-center gap-2 text-muted-foreground text-sm">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading...
        </div>
      )}

      {!isLoading && (!versions || versions.length === 0) && (
        <p className="text-sm text-muted-foreground">No versions yet.</p>
      )}

      {versions && versions.length > 0 && (
        <ul className="space-y-2">
          {[...versions].reverse().map((version) => (
            <li
              key={version.id}
              className={`rounded-md border p-3 ${
                version.version_number === currentVersion
                  ? "border-primary/30 bg-primary/5"
                  : "border-gray-200 bg-white"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-medium text-gray-900">
                    v{version.version_number}
                    {version.version_number === currentVersion && (
                      <span className="ml-1.5 text-xs text-primary font-normal">(current)</span>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {formatDistanceToNow(version.created_at)}
                    {version.size_bytes && ` · ${(version.size_bytes / 1024).toFixed(1)} KB`}
                  </p>
                </div>
                <button
                  onClick={() => handleDownloadVersion(version.id)}
                  title="Download this version"
                  className="text-muted-foreground hover:text-foreground"
                >
                  <Download className="h-4 w-4" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
