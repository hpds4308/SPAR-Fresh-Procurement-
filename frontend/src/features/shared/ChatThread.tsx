import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import {
  ATTACHMENT_ACCEPT,
  Attachment,
  MAX_ATTACHMENTS,
  MAX_ATTACHMENT_BYTES,
  Message,
  attachmentUrl,
  uploadAttachment,
} from "../../api/messages";
import { IconFile, IconPaperclip } from "./Icons";

function formatTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" }) + " " +
    d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const isImage = (contentType: string) => contentType.startsWith("image/");

// Phone photos are often 3–8 MB; they're shrunk before upload so they fit
// the 5 MB limit and don't fill the (small) database.
const MAX_IMAGE_SIDE = 1600;

async function shrinkImage(file: File): Promise<File> {
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size < 500 * 1024) return file;
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, MAX_IMAGE_SIDE / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.fillStyle = "#fff"; // a transparent PNG becomes a JPEG on white
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
    if (!blob || blob.size >= file.size) return file;
    const name = file.name.replace(/\.[^.]+$/, "") + ".jpg";
    return new File([blob], name, { type: "image/jpeg" });
  } catch {
    return file;
  }
}

/** Opens a photo/PDF in a new tab, or downloads any other file. */
async function openAttachment(a: Attachment) {
  const url = await attachmentUrl(a.id);
  if (isImage(a.content_type) || a.content_type === "application/pdf") {
    window.open(url, "_blank", "noopener");
    return;
  }
  const link = document.createElement("a");
  link.href = url;
  link.download = a.filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

function AttachmentImage({ attachment }: { attachment: Attachment }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let cancelled = false;
    attachmentUrl(attachment.id)
      .then((url) => !cancelled && setSrc(url))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [attachment.id]);
  if (failed) return <AttachmentFile attachment={attachment} mine={false} />;
  return (
    <button
      type="button"
      onClick={() => openAttachment(attachment)}
      title={`${attachment.filename} — open full size`}
      className="block rounded-xl overflow-hidden bg-sage-100 border border-sage-200 w-48 h-36"
    >
      {src ? (
        <img src={src} alt={attachment.filename} className="w-full h-full object-cover" />
      ) : (
        <span className="block w-full h-full animate-pulse" />
      )}
    </button>
  );
}

function AttachmentFile({ attachment, mine }: { attachment: Attachment; mine: boolean }) {
  return (
    <button
      type="button"
      onClick={() => openAttachment(attachment)}
      title={`Open ${attachment.filename}`}
      className={`flex items-center gap-2 rounded-xl px-3 py-2 text-left max-w-[16rem] border transition-colors ${
        mine
          ? "bg-crate-800 border-crate-600 text-white hover:bg-crate-900"
          : "bg-white border-sage-200 text-crate-950 hover:bg-sage-50"
      }`}
    >
      <IconFile width={18} height={18} className="shrink-0" />
      <span className="min-w-0">
        <span className="block text-sm truncate">{attachment.filename}</span>
        <span className={`block text-[10px] ${mine ? "text-white/60" : "text-crate-800/45"}`}>
          {formatSize(attachment.size_bytes)}
        </span>
      </span>
    </button>
  );
}

type Pending = {
  key: number;
  name: string;
  status: "uploading" | "done" | "error";
  attachment?: Attachment;
  error?: string;
  previewUrl?: string;
};

export default function ChatThread({
  messages,
  currentRole,
  onSend,
  emptyHint,
  readOnly = false,
  senderLabel,
}: {
  messages: Message[];
  currentRole: "ADMIN" | "SUPPLIER" | "BRANCH";
  onSend?: (body: string, attachmentIds: number[]) => Promise<void>;
  emptyHint: string;
  // No message box — for Admin looking in on a supplier <-> branch chat.
  readOnly?: boolean;
  // Name shown under a message; defaults to "You" / the sender's username.
  senderLabel?: (m: Message, mine: boolean) => string;
}) {
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<Pending[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const nextKey = useRef(1);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length]);

  const uploading = pending.some((p) => p.status === "uploading");
  const ready = pending.filter((p) => p.status === "done");
  const canSend = !sending && !uploading && (draft.trim() !== "" || ready.length > 0);

  // Files upload as soon as they're picked, so Send is quick.
  async function addFiles(files: File[]) {
    setError(null);
    const room = MAX_ATTACHMENTS - pending.length;
    if (room <= 0) {
      setError(`You can attach up to ${MAX_ATTACHMENTS} files to one message.`);
      return;
    }
    if (files.length > room) setError(`Only the first ${room} file${room === 1 ? "" : "s"} were added (max ${MAX_ATTACHMENTS}).`);
    for (const original of files.slice(0, room)) {
      const key = nextKey.current++;
      setPending((prev) => [...prev, { key, name: original.name, status: "uploading" }]);
      (async () => {
        const file = await shrinkImage(original);
        if (file.size > MAX_ATTACHMENT_BYTES) {
          throw new ApiError(400, `${original.name} is too large — files can be up to 5 MB.`);
        }
        const attachment = await uploadAttachment(file);
        const previewUrl = isImage(file.type) ? URL.createObjectURL(file) : undefined;
        setPending((prev) => prev.map((p) => (p.key === key ? { ...p, status: "done", attachment, previewUrl } : p)));
      })().catch((err) => {
        const message = err instanceof ApiError ? err.message : `${original.name} couldn't be uploaded.`;
        setPending((prev) => prev.map((p) => (p.key === key ? { ...p, status: "error", error: message } : p)));
      });
    }
  }

  function removePending(key: number) {
    setPending((prev) => {
      const gone = prev.find((p) => p.key === key);
      if (gone?.previewUrl) URL.revokeObjectURL(gone.previewUrl);
      return prev.filter((p) => p.key !== key);
    });
  }

  async function handleSend() {
    const body = draft.trim();
    if (!canSend || !onSend) return;
    setSending(true);
    setError(null);
    try {
      await onSend(body, ready.map((p) => p.attachment!.id));
      setDraft("");
      pending.forEach((p) => p.previewUrl && URL.revokeObjectURL(p.previewUrl));
      setPending([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Message didn't send — try again.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.length === 0 ? (
          <p className="text-sm text-crate-800/35 text-center mt-10">{emptyHint}</p>
        ) : (
          messages.map((m) => {
            const mine = m.sender_role === currentRole;
            const attachments = m.attachments ?? [];
            const images = attachments.filter((a) => isImage(a.content_type));
            const files = attachments.filter((a) => !isImage(a.content_type));
            return (
              <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[75%] ${mine ? "items-end" : "items-start"} flex flex-col gap-1`}>
                  {images.length > 0 && (
                    <div className={`flex flex-wrap gap-1.5 ${mine ? "justify-end" : ""}`}>
                      {images.map((a) => (
                        <AttachmentImage key={a.id} attachment={a} />
                      ))}
                    </div>
                  )}
                  {files.map((a) => (
                    <AttachmentFile key={a.id} attachment={a} mine={mine} />
                  ))}
                  {m.body && (
                    <div
                      className={`rounded-2xl px-3.5 py-2 text-sm whitespace-pre-wrap break-words ${
                        mine
                          ? "bg-crate-700 text-white rounded-br-sm"
                          : "bg-sage-100 text-crate-950 rounded-bl-sm"
                      }`}
                    >
                      {m.body}
                    </div>
                  )}
                  <span className="text-[10px] text-crate-800/35 px-1">
                    {senderLabel ? senderLabel(m, mine) : mine ? "You" : m.sender_username} · {formatTime(m.created_at)}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>

      {!readOnly && (
        <div
          className="border-t border-sage-100 p-3"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            if (e.dataTransfer.files.length) addFiles(Array.from(e.dataTransfer.files));
          }}
        >
          {error && <p className="text-tomato-600 text-xs mb-1.5 px-1">{error}</p>}
          {pending.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {pending.map((p) => (
                <div
                  key={p.key}
                  className={`relative flex items-center gap-2 rounded-xl border pl-2 pr-7 py-1.5 text-xs max-w-[14rem] ${
                    p.status === "error" ? "border-tomato-500/40 bg-tomato-500/5" : "border-sage-200 bg-sage-50"
                  }`}
                  title={p.error ?? p.name}
                >
                  {p.previewUrl ? (
                    <img src={p.previewUrl} alt="" className="w-8 h-8 rounded object-cover shrink-0" />
                  ) : (
                    <IconFile width={16} height={16} className="shrink-0 text-crate-800/60" />
                  )}
                  <span className="min-w-0">
                    <span className="block truncate text-crate-950">{p.name}</span>
                    <span className={`block text-[10px] ${p.status === "error" ? "text-tomato-600" : "text-crate-800/45"}`}>
                      {p.status === "uploading"
                        ? "Uploading…"
                        : p.status === "error"
                        ? p.error
                        : formatSize(p.attachment!.size_bytes)}
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={() => removePending(p.key)}
                    className="absolute top-1 right-1.5 text-crate-800/40 hover:text-tomato-600 text-sm leading-none"
                    aria-label={`Remove ${p.name}`}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="flex items-end gap-2">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={ATTACHMENT_ACCEPT}
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.length) addFiles(Array.from(e.target.files));
                e.target.value = "";
              }}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={pending.length >= MAX_ATTACHMENTS}
              className="shrink-0 w-9 h-9 inline-flex items-center justify-center rounded-full text-crate-700 hover:bg-sage-100 disabled:opacity-40 transition-colors"
              aria-label="Attach photos or files"
              title="Attach photos or files (up to 5, 5 MB each)"
            >
              <IconPaperclip width={19} height={19} />
            </button>
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              onPaste={(e) => {
                // Pasting a screenshot attaches it.
                const files = Array.from(e.clipboardData.files);
                if (files.length) {
                  e.preventDefault();
                  addFiles(files);
                }
              }}
              placeholder="Write a message…"
              rows={1}
              className="flex-1 resize-none border border-sage-300 bg-sage-50/60 rounded-2xl px-3.5 py-2 text-sm max-h-24 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
            />
            <button
              onClick={handleSend}
              disabled={!canSend}
              className="text-sm bg-crate-700 text-white rounded-full px-4 py-2 font-semibold hover:bg-crate-800 active:scale-[0.98] disabled:opacity-40 disabled:active:scale-100 transition-all duration-150 shrink-0"
            >
              {sending ? "…" : "Send"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
