import React, { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  FileText,
  FileSpreadsheet,
  FileCode2,
  Image as ImageIcon,
  Download,
  Eye,
  EyeOff,
  Loader2,
  Sparkles,
  GitCommit,
  Check,
  AlertTriangle,
} from "lucide-react";
import { getToken } from "../auth";
import { CodeBlock } from "./CodeBlock";
import { getFileIcon } from "./FileChip";

// Simple CSV parser for small table previews
function parseCsvRows(text, maxRows = 15) {
  if (!text) return { headers: [], rows: [] };
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length === 0) return { headers: [], rows: [] };

  const parseLine = (line) => {
    const result = [];
    let current = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      if (char === '"') {
        inQuotes = !inQuotes;
      } else if (char === "," && !inQuotes) {
        result.push(current.trim());
        current = "";
      } else {
        current += char;
      }
    }
    result.push(current.trim());
    return result;
  };

  const headers = parseLine(lines[0]);
  const rows = lines.slice(1, maxRows + 1).map(parseLine);
  return { headers, rows, totalLines: lines.length - 1 };
}

export function FileCard({ file, isStreaming = false }) {
  const { id, name, kind, version = 1, download_url, parent, spec } = file;
  const [showPreview, setShowPreview] = useState(false);
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState(null);
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadSuccess, setDownloadSuccess] = useState(false);

  const isReady = Boolean(download_url) && !isStreaming;
  const IconComponent = getFileIcon(name);

  // Authenticated blob download: Bearer token is strictly in header, NEVER in query string URL
  const handleDownload = async () => {
    if (!download_url || isDownloading) return;
    setIsDownloading(true);
    setDownloadSuccess(false);

    try {
      const token = await getToken();
      const response = await fetch(download_url, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error(`Download failed with status ${response.status}`);
      }

      const blob = await response.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const downloadLink = document.createElement("a");
      downloadLink.href = blobUrl;
      downloadLink.download = name || "download";
      document.body.appendChild(downloadLink);
      downloadLink.click();
      downloadLink.remove();

      // Revoke blob URL after slight delay to ensure browser initiated download
      setTimeout(() => {
        window.URL.revokeObjectURL(blobUrl);
      }, 2000);

      setDownloadSuccess(true);
      setTimeout(() => setDownloadSuccess(false), 2500);
    } catch (err) {
      console.error("Authenticated blob download failed:", err);
      alert("Failed to download file: " + (err.message || "Unknown error"));
    } finally {
      setIsDownloading(false);
    }
  };

  // Load preview data when toggle is enabled or when file revision updates
  useEffect(() => {
    let active = true;
    let createdObjectUrl = null;

    if (!showPreview) {
      return;
    }

    const loadPreview = async () => {
      setPreviewLoading(true);
      setPreviewError(null);

      try {
        const token = await getToken();
        const ext = name.split(".").pop()?.toLowerCase() || kind;

        // Image / PNG chart preview
        if (ext === "png" || ext === "jpg" || ext === "jpeg" || ext === "webp" || kind === "chart") {
          const res = await fetch(download_url, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!res.ok) throw new Error(`Preview failed (${res.status})`);
          const blob = await res.blob();
          if (active) {
            createdObjectUrl = window.URL.createObjectURL(blob);
            setPreviewData({ type: "image", url: createdObjectUrl });
          }
          return;
        }

        // Markdown preview
        if (ext === "md" || kind === "md") {
          if (spec && typeof spec.content === "string") {
            setPreviewData({ type: "markdown", content: spec.content });
            return;
          }
          const res = await fetch(download_url, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!res.ok) throw new Error(`Preview failed (${res.status})`);
          const text = await res.text();
          if (active) setPreviewData({ type: "markdown", content: text });
          return;
        }

        // CSV preview
        if (ext === "csv" || kind === "csv") {
          if (spec && Array.isArray(spec.rows)) {
            const headers = Array.isArray(spec.headers) ? spec.headers : [];
            setPreviewData({
              type: "table",
              headers,
              rows: spec.rows.slice(0, 15),
              totalLines: spec.rows.length,
            });
            return;
          }
          const res = await fetch(download_url, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!res.ok) throw new Error(`Preview failed (${res.status})`);
          const text = await res.text();
          if (active) {
            const parsed = parseCsvRows(text, 15);
            setPreviewData({ type: "table", ...parsed });
          }
          return;
        }

        // XLSX preview: fetch cached values (data_only) from backend preview endpoint
        if (ext === "xlsx" || kind === "xlsx") {
          try {
            const pRes = await fetch(`/api/generated/${id}/preview/`, {
              headers: { Authorization: `Bearer ${token}` },
            });
            if (pRes.ok) {
              const pData = await pRes.json();
              if (active && pData && Array.isArray(pData.rows)) {
                setPreviewData({
                  type: "table",
                  headers: pData.headers || [],
                  rows: pData.rows,
                  totalLines: pData.total_rows || pData.rows.length,
                  warning: pData.warning,
                  has_uncalculated_formulas: pData.has_uncalculated_formulas,
                });
                return;
              }
            }
          } catch (e) {
            // fallback to spec if preview endpoint fails
          }

          if (spec && Array.isArray(spec.rows)) {
            const headers = Array.isArray(spec.headers) ? spec.headers : [];
            const normalizedRows = spec.rows.map((r) =>
              Array.isArray(r)
                ? r.map((c) => (c && typeof c === "object" ? c.value ?? "" : c))
                : [r]
            );
            const hasFormulaWithoutVal = spec.rows.some((r) =>
              Array.isArray(r) &&
              r.some(
                (c) =>
                  (typeof c === "string" && c.startsWith("=")) ||
                  (c && typeof c === "object" && c.formula && c.value === null)
              )
            );
            setPreviewData({
              type: "table",
              headers,
              rows: normalizedRows,
              totalLines: normalizedRows.length,
              warning: hasFormulaWithoutVal ? "formulas not calculated" : null,
              has_uncalculated_formulas: hasFormulaWithoutVal,
            });
            return;
          }
          if (spec && spec.sheets) {
            const firstSheet = Object.values(spec.sheets)[0];
            if (firstSheet && Array.isArray(firstSheet.rows)) {
              const headers = firstSheet.headers || [];
              const normalizedRows = firstSheet.rows.map((r) =>
                Array.isArray(r)
                  ? r.map((c) => (c && typeof c === "object" ? c.value ?? "" : c))
                  : [r]
              );
              setPreviewData({
                type: "table",
                headers,
                rows: normalizedRows,
                totalLines: normalizedRows.length,
                warning: null,
                has_uncalculated_formulas: false,
              });
              return;
            }
          }
          setPreviewData({
            type: "document",
            summary: spec ? JSON.stringify(spec, null, 2) : "Excel spreadsheet ready for download.",
          });
          return;
        }

        // Code / Text preview
        if (
          ["py", "js", "ts", "jsx", "tsx", "json", "html", "css", "txt"].includes(ext) ||
          kind === "code"
        ) {
          if (spec && typeof spec.code === "string") {
            setPreviewData({ type: "code", language: ext === "py" ? "python" : ext, code: spec.code });
            return;
          }
          const res = await fetch(download_url, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!res.ok) throw new Error(`Preview failed (${res.status})`);
          const text = await res.text();
          if (active) setPreviewData({ type: "code", language: ext, code: text });
          return;
        }

        // Fallback for docx / pdf / pptx: render spec overview
        setPreviewData({
          type: "document",
          summary: spec
            ? typeof spec.content === "string"
              ? spec.content
              : JSON.stringify(spec, null, 2)
            : `${kind.toUpperCase()} document generated and ready for download.`,
        });
      } catch (err) {
        if (active) {
          setPreviewError(err.message || "Failed to load inline preview.");
        }
      } finally {
        if (active) setPreviewLoading(false);
      }
    };

    loadPreview();

    return () => {
      active = false;
      if (createdObjectUrl) {
        window.URL.revokeObjectURL(createdObjectUrl);
      }
    };
  }, [showPreview, id, version, download_url, name, kind, spec]);

  // Clean format for file kind label
  const getKindLabel = (k = "") => {
    switch (k.toLowerCase()) {
      case "chart":
      case "png":
        return "CHART PNG";
      case "md":
        return "MARKDOWN";
      case "csv":
        return "CSV DATA";
      case "xlsx":
        return "EXCEL";
      case "code":
        return "SOURCE CODE";
      case "docx":
        return "DOCX WORD";
      case "pdf":
        return "PDF DOCUMENT";
      case "pptx":
        return "POWERPOINT";
      default:
        return k.toUpperCase() || "FILE";
    }
  };

  return (
    <div className="generated-file-card" id={`file-card-${id}`}>
      {/* File Card Header */}
      <div className="file-card-header">
        <div className="file-card-left">
          <div className="file-card-icon-box">
            <IconComponent size={20} className="file-card-icon" />
          </div>
          <div className="file-card-info">
            <div className="file-card-title-row">
              <span className="file-card-name" title={name}>
                {name}
              </span>
              <span className="version-indicator" title={`Version ${version}`}>
                v{version}
              </span>
              {parent && (
                <span className="revision-pill" title="Revised from earlier version">
                  <GitCommit size={11} style={{ marginRight: "3px" }} />
                  revised
                </span>
              )}
            </div>
            <div className="file-card-kind-badge">{getKindLabel(kind)}</div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="file-card-actions">
          <button
            type="button"
            className={`file-card-btn preview-toggle-btn ${showPreview ? "active" : ""}`}
            onClick={() => setShowPreview((prev) => !prev)}
            disabled={!isReady}
            title={
              !isReady
                ? "Preview available once generation finishes"
                : showPreview
                ? "Hide preview"
                : "View inline preview"
            }
          >
            {showPreview ? <EyeOff size={14} /> : <Eye size={14} />}
            <span>{showPreview ? "Hide" : "Preview"}</span>
          </button>

          <button
            type="button"
            className={`file-card-btn download-btn ${downloadSuccess ? "success" : ""}`}
            onClick={handleDownload}
            disabled={!isReady || isDownloading}
            title={
              isStreaming
                ? "Download available once generation finishes"
                : !download_url
                ? "Preparing download link..."
                : "Download file securely via Bearer token"
            }
          >
            {isDownloading ? (
              <>
                <Loader2 size={14} className="spin-icon" />
                <span>Downloading...</span>
              </>
            ) : isStreaming ? (
              <>
                <Loader2 size={14} className="spin-icon" />
                <span>Generating...</span>
              </>
            ) : !download_url ? (
              <>
                <Loader2 size={14} className="spin-icon" />
                <span>Preparing...</span>
              </>
            ) : downloadSuccess ? (
              <>
                <Check size={14} color="#10b981" />
                <span>Downloaded!</span>
              </>
            ) : (
              <>
                <Download size={14} />
                <span>Download</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Inline Preview Section */}
      {showPreview && (
        <div className="file-card-preview-body">
          {previewLoading && (
            <div className="preview-loading-state">
              <Loader2 size={20} className="spin-icon" />
              <span>Loading authenticated preview...</span>
            </div>
          )}

          {previewError && (
            <div className="preview-error-state">
              <span>{previewError}</span>
            </div>
          )}

          {!previewLoading && !previewError && previewData && (
            <div className="preview-content-area">
              {/* Image / Chart preview */}
              {previewData.type === "image" && (
                <div className="preview-image-wrapper">
                  <img
                    src={previewData.url}
                    alt={name}
                    className="preview-image"
                    loading="lazy"
                  />
                </div>
              )}

              {/* Rendered Markdown preview */}
              {previewData.type === "markdown" && (
                <div className="preview-markdown-wrapper markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {previewData.content}
                  </ReactMarkdown>
                </div>
              )}

              {/* CSV / XLSX Small Table preview */}
              {previewData.type === "table" && (
                <div className="preview-table-wrapper">
                  {previewData.warning && (
                    <div className="preview-formula-warning" style={{ display: "flex", alignItems: "center", gap: "8px", padding: "8px 12px", background: "rgba(234, 179, 8, 0.12)", border: "1px solid rgba(234, 179, 8, 0.35)", borderRadius: "6px", color: "#facc15", fontSize: "0.85rem", marginBottom: "10px" }}>
                      <AlertTriangle size={15} />
                      <span>Warning: {previewData.warning}</span>
                    </div>
                  )}
                  <div className="preview-table-scroll">
                    <table className="preview-data-table">
                      {previewData.headers && previewData.headers.length > 0 && (
                        <thead>
                          <tr>
                            {previewData.headers.map((h, i) => (
                              <th key={i}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                      )}
                      <tbody>
                        {previewData.rows.map((row, rIdx) => {
                          const isTotal = row[0] && String(row[0]).trim().toLowerCase() === "total";
                          return (
                            <tr key={rIdx} style={isTotal ? { fontWeight: "bold", background: "rgba(255, 255, 255, 0.06)", borderTop: "2px solid rgba(255, 255, 255, 0.25)" } : {}}>
                              {row.map((cell, cIdx) => (
                                <td key={cIdx} style={isTotal ? { fontWeight: "bold" } : {}}>{cell !== null && cell !== undefined ? String(cell) : ""}</td>
                              ))}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Code Preview */}
              {previewData.type === "code" && (
                <div className="preview-code-wrapper">
                  <CodeBlock
                    language={previewData.language || "javascript"}
                    value={previewData.code || ""}
                  />
                </div>
              )}

              {/* Document Overview Preview */}
              {previewData.type === "document" && (
                <div className="preview-document-wrapper">
                  <div className="preview-document-badge">
                    <Sparkles size={14} />
                    <span>Specification Overview</span>
                  </div>
                  <pre className="preview-document-text">{previewData.summary}</pre>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
