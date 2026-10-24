import React, { useState, useRef, useCallback } from "react";
import {
  Send,
  Square,
  Paperclip,
  UploadCloud,
  AlertTriangle,
} from "lucide-react";
import { getToken } from "../auth";
import { FileChip } from "./FileChip";

const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024; // 25 MB
const MAX_REQUEST_SIZE_BYTES = 100 * 1024 * 1024; // 100 MB

const ALLOWED_EXTENSIONS = new Set([
  "pdf",
  "docx",
  "xlsx",
  "csv",
  "pptx",
  "png",
  "jpg",
  "jpeg",
  "gif",
  "webp",
  "txt",
  "md",
  "py",
  "js",
  "ts",
  "tsx",
  "jsx",
  "json",
  "zip",
]);

export function Composer({
  threadId,
  isStreaming,
  onSend,
  onStop,
  statusText,
}) {
  const [inputText, setInputText] = useState("");
  const [files, setFiles] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const [composerError, setComposerError] = useState(null);

  const fileInputRef = useRef(null);
  const textareaRef = useRef(null);
  const dragCounterRef = useRef(0);
  const activeXhrsRef = useRef(new Map());

  // Upload single file with XMLHttpRequest for fine-grained per-file progress
  const uploadSingleFile = async (fileObj, tempId) => {
    try {
      const token = await getToken();
      const xhr = new XMLHttpRequest();
      activeXhrsRef.current.set(tempId, xhr);

      const formData = new FormData();
      formData.append("files", fileObj);

      // Track byte-by-byte upload progress
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const percent = Math.min(99, Math.round((event.loaded / event.total) * 100));
          setFiles((prev) =>
            prev.map((f) => (f.tempId === tempId ? { ...f, progress: percent } : f))
          );
        }
      };

      // When bytes are fully uploaded, mark status as parsing until server response finishes
      xhr.upload.onload = () => {
        setFiles((prev) =>
          prev.map((f) => (f.tempId === tempId ? { ...f, status: "parsing", progress: 100 } : f))
        );
      };

      xhr.onload = () => {
        activeXhrsRef.current.delete(tempId);
        if (xhr.status >= 200 && xhr.status < 300) {
          let responseData;
          try {
            responseData = JSON.parse(xhr.responseText);
          } catch {
            responseData = [];
          }

          const uploadedRecord = Array.isArray(responseData) ? responseData[0] : responseData;

          if (uploadedRecord && uploadedRecord.status === "failed") {
            setFiles((prev) =>
              prev.map((f) =>
                f.tempId === tempId
                  ? {
                      ...f,
                      status: "failed",
                      error: uploadedRecord.error || "File parsing failed on server",
                    }
                  : f
              )
            );
          } else if (uploadedRecord) {
            setFiles((prev) =>
              prev.map((f) =>
                f.tempId === tempId
                  ? {
                      ...f,
                      id: uploadedRecord.id,
                      status: "ready",
                      backendFile: uploadedRecord,
                    }
                  : f
              )
            );
          }
        } else {
          let errorMsg = `Upload failed (${xhr.status})`;
          try {
            const errObj = JSON.parse(xhr.responseText);
            errorMsg = errObj.detail || errObj.error || errorMsg;
          } catch {}
          setFiles((prev) =>
            prev.map((f) =>
              f.tempId === tempId ? { ...f, status: "failed", error: errorMsg } : f
            )
          );
        }
      };

      xhr.onerror = () => {
        activeXhrsRef.current.delete(tempId);
        setFiles((prev) =>
          prev.map((f) =>
            f.tempId === tempId ? { ...f, status: "failed", error: "Network connection error" } : f
          )
        );
      };

      xhr.open("POST", `/api/threads/${threadId}/files/`);
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.send(formData);
    } catch (err) {
      activeXhrsRef.current.delete(tempId);
      setFiles((prev) =>
        prev.map((f) =>
          f.tempId === tempId
            ? { ...f, status: "failed", error: err.message || "Failed to start upload" }
            : f
        )
      );
    }
  };

  // Validate and enqueue files from drop or picker
  const handleAddFiles = useCallback(
    (fileList) => {
      if (!fileList || fileList.length === 0) return;
      if (!threadId) {
        setComposerError("Please select or create a conversation before attaching files.");
        return;
      }

      setComposerError(null);
      const incoming = Array.from(fileList);

      // Total batch size check
      const currentTotalSize = files.reduce((acc, f) => acc + (f.size || 0), 0);
      const incomingTotalSize = incoming.reduce((acc, f) => acc + (f.size || 0), 0);
      if (currentTotalSize + incomingTotalSize > MAX_REQUEST_SIZE_BYTES) {
        setComposerError("Total batch upload size exceeds maximum allowed limit of 100 MB.");
        return;
      }

      incoming.forEach((file) => {
        const ext = file.name.split(".").pop()?.toLowerCase();
        const tempId = "temp-" + Date.now() + "-" + Math.random().toString(36).slice(2, 7);

        // Check unsupported extension
        if (!ext || !ALLOWED_EXTENSIONS.has(ext)) {
          setFiles((prev) => [
            ...prev,
            {
              tempId,
              name: file.name,
              size: file.size,
              status: "failed",
              error: `Unsupported file type (.${ext || "unknown"}). Supported: PDF, DOCX, XLSX, CSV, PPTX, Images, Code/Text, ZIP`,
            },
          ]);
          return;
        }

        // Check single file size limit (> 25MB)
        if (file.size > MAX_FILE_SIZE_BYTES) {
          const mb = (file.size / (1024 * 1024)).toFixed(1);
          setFiles((prev) => [
            ...prev,
            {
              tempId,
              name: file.name,
              size: file.size,
              status: "failed",
              error: `File exceeds 25 MB limit (${mb} MB)`,
            },
          ]);
          return;
        }

        // File is valid: add to list and start upload
        const newFile = {
          tempId,
          name: file.name,
          size: file.size,
          status: "uploading",
          progress: 0,
        };

        setFiles((prev) => [...prev, newFile]);
        uploadSingleFile(file, tempId);
      });
    },
    [threadId, files]
  );

  const handleRemoveFile = (targetId) => {
    // Abort active XHR if ongoing
    if (activeXhrsRef.current.has(targetId)) {
      activeXhrsRef.current.get(targetId).abort();
      activeXhrsRef.current.delete(targetId);
    }
    setFiles((prev) => prev.filter((f) => f.tempId !== targetId && f.id !== targetId));
  };

  const handleDragEnter = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current += 1;
    if (e.dataTransfer?.items && e.dataTransfer.items.length > 0) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current -= 1;
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0;
      setIsDragging(false);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current = 0;
    setIsDragging(false);

    if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
      handleAddFiles(e.dataTransfer.files);
    }
  };

  const handleFilePickerChange = (e) => {
    if (e.target.files) {
      handleAddFiles(e.target.files);
      e.target.value = "";
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    const isAnyUploading = files.some((f) => f.status === "uploading" || f.status === "parsing");
    if (isAnyUploading || isStreaming) return;

    const trimmed = inputText.trim();
    const readyFiles = files.filter((f) => f.status === "ready");

    if (!trimmed && readyFiles.length === 0) return;

    onSend(trimmed, readyFiles);
    setInputText("");
    // Clear successfully attached files from composer
    setFiles([]);
    setComposerError(null);

    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleTextareaInput = (e) => {
    setInputText(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
  };

  const isAnyUploading = files.some((f) => f.status === "uploading" || f.status === "parsing");
  const canSend = (inputText.trim().length > 0 || files.some((f) => f.status === "ready")) && !isAnyUploading && !isStreaming;

  return (
    <div
      className={`composer-wrapper ${isDragging ? "drag-over" : ""}`}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        style={{ display: "none" }}
        onChange={handleFilePickerChange}
        accept=".pdf,.docx,.xlsx,.csv,.pptx,.png,.jpg,.jpeg,.gif,.webp,.txt,.md,.py,.js,.ts,.tsx,.jsx,.json,.zip"
      />

      {/* Drag & Drop Visual Overlay */}
      {isDragging && (
        <div className="drag-drop-overlay">
          <UploadCloud size={40} className="drag-drop-icon" />
          <span className="drag-drop-title">Drop files to attach</span>
          <span className="drag-drop-subtitle">PDF, Word, Excel, CSV, PPTX, Images, Code, ZIP (up to 25MB)</span>
        </div>
      )}

      {/* Active File Chips Tray */}
      {files.length > 0 && (
        <div className="composer-files-tray">
          {files.map((file) => (
            <FileChip
              key={file.tempId || file.id}
              file={file}
              onRemove={() => handleRemoveFile(file.tempId || file.id)}
            />
          ))}
        </div>
      )}

      {/* Composer Error Notice */}
      {composerError && (
        <div className="composer-error-banner">
          <AlertTriangle size={14} />
          <span>{composerError}</span>
          <button
            type="button"
            className="composer-error-close"
            onClick={() => setComposerError(null)}
          >
            ×
          </button>
        </div>
      )}

      {/* Input Box */}
      <div className="input-box-wrapper">
        <textarea
          ref={textareaRef}
          className="chat-textarea"
          placeholder={
            files.length > 0
              ? "Add instructions for attached files, or press Enter..."
              : "Send a message or attach files (drag & drop or click clip)..."
          }
          rows={1}
          value={inputText}
          onChange={handleTextareaInput}
          onKeyDown={handleKeyDown}
          disabled={isStreaming}
        />

        <div className="input-bottom-row">
          <div className="input-left-tools">
            <button
              type="button"
              className="attach-btn"
              onClick={() => fileInputRef.current?.click()}
              title="Attach files (PDF, DOCX, XLSX, CSV, Images, Code, ZIP - max 25MB)"
              disabled={isStreaming}
            >
              <Paperclip size={16} />
              <span className="attach-btn-label">Attach</span>
            </button>

            <span className="input-hint">
              {isStreaming ? (
                <span style={{ color: "var(--accent-primary)" }}>{statusText || "Streaming response..."}</span>
              ) : isAnyUploading ? (
                <span style={{ color: "var(--accent-primary)" }}>Uploading & parsing files...</span>
              ) : (
                "Drag & drop files or type Enter to send"
              )}
            </span>
          </div>

          <div className="input-actions">
            {isStreaming ? (
              <button
                type="button"
                className="stop-btn"
                onClick={onStop}
                title="Stop response generation"
              >
                <Square size={13} fill="currentColor" />
                <span>Stop</span>
              </button>
            ) : (
              <button
                type="button"
                className="send-btn"
                onClick={handleSubmit}
                disabled={!canSend}
                title="Send message"
              >
                <Send size={15} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
