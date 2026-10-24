import React from "react";
import {
  FileText,
  FileSpreadsheet,
  FileCode2,
  FileArchive,
  Image as ImageIcon,
  File,
  X,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from "lucide-react";

// Format bytes into human readable string
export function formatBytes(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

// Return appropriate Lucide icon component according to filename extension
export function getFileIcon(filename = "") {
  const ext = filename.split(".").pop()?.toLowerCase();
  switch (ext) {
    case "pdf":
    case "docx":
    case "doc":
    case "txt":
    case "md":
      return FileText;
    case "csv":
    case "xlsx":
    case "xls":
      return FileSpreadsheet;
    case "py":
    case "js":
    case "ts":
    case "tsx":
    case "jsx":
    case "json":
    case "html":
    case "css":
    case "sql":
      return FileCode2;
    case "zip":
    case "tar":
    case "gz":
      return FileArchive;
    case "png":
    case "jpg":
    case "jpeg":
    case "gif":
    case "webp":
      return ImageIcon;
    default:
      return File;
  }
}

export function FileChip({ file, onRemove, readOnly = false }) {
  const { name, size, status = "ready", progress = 0, error } = file;
  const IconComponent = getFileIcon(name);

  return (
    <div className={`file-chip status-${status}`} title={error || name}>
      <div className="file-chip-icon-wrapper">
        <IconComponent size={15} className="file-chip-type-icon" />
      </div>

      <div className="file-chip-content">
        <div className="file-chip-name-row">
          <span className="file-chip-name">{name}</span>
          {size > 0 && <span className="file-chip-size">({formatBytes(size)})</span>}
        </div>

        {/* Status indicator row */}
        <div className="file-chip-status-row">
          {status === "uploading" && (
            <div className="file-chip-progress-container">
              <div className="file-chip-progress-bar">
                <div
                  className="file-chip-progress-fill"
                  style={{ width: `${Math.max(0, Math.min(100, progress))}%` }}
                />
              </div>
              <span className="file-chip-status-text">{progress}%</span>
            </div>
          )}

          {status === "parsing" && (
            <div className="file-chip-parsing">
              <Loader2 size={12} className="spin-icon" />
              <span className="file-chip-status-text">Parsing file...</span>
            </div>
          )}

          {status === "ready" && (
            <div className="file-chip-ready">
              <CheckCircle2 size={12} className="check-icon" />
              <span className="file-chip-status-text">Ready</span>
            </div>
          )}

          {status === "failed" && (
            <div className="file-chip-failed" title={error}>
              <AlertCircle size={12} className="fail-icon" />
              <span className="file-chip-status-text file-chip-error-msg">
                {error || "Upload failed"}
              </span>
            </div>
          )}
        </div>
      </div>

      {!readOnly && onRemove && (
        <button
          type="button"
          className="file-chip-remove-btn"
          onClick={() => onRemove(file.id || file.name)}
          title="Remove file"
          aria-label={`Remove ${name}`}
        >
          <X size={13} />
        </button>
      )}
    </div>
  );
}
