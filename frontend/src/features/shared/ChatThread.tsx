import { useEffect, useRef, useState } from "react";
import { Message } from "../../api/messages";

function formatTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" }) + " " +
    d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export default function ChatThread({
  messages,
  currentRole,
  onSend,
  emptyHint,
}: {
  messages: Message[];
  currentRole: "ADMIN" | "SUPPLIER" | "BRANCH";
  onSend: (body: string) => Promise<void>;
  emptyHint: string;
}) {
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length]);

  async function handleSend() {
    const body = draft.trim();
    if (!body || sending) return;
    setSending(true);
    setError(null);
    try {
      await onSend(body);
      setDraft("");
    } catch {
      setError("Message didn't send — try again.");
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
            return (
              <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[75%] ${mine ? "items-end" : "items-start"} flex flex-col gap-0.5`}>
                  <div
                    className={`rounded-2xl px-3.5 py-2 text-sm whitespace-pre-wrap break-words ${
                      mine
                        ? "bg-crate-700 text-white rounded-br-sm"
                        : "bg-sage-100 text-crate-950 rounded-bl-sm"
                    }`}
                  >
                    {m.body}
                  </div>
                  <span className="text-[10px] text-crate-800/35 px-1">
                    {mine ? "You" : m.sender_username} · {formatTime(m.created_at)}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>

      <div className="border-t border-sage-100 p-3">
        {error && <p className="text-tomato-600 text-xs mb-1.5 px-1">{error}</p>}
        <div className="flex items-end gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Write a message…"
            rows={1}
            className="flex-1 resize-none border border-sage-300 bg-sage-50/60 rounded-2xl px-3.5 py-2 text-sm max-h-24 focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
          />
          <button
            onClick={handleSend}
            disabled={sending || !draft.trim()}
            className="text-sm bg-crate-700 text-white rounded-full px-4 py-2 font-semibold hover:bg-crate-800 active:scale-[0.98] disabled:opacity-40 disabled:active:scale-100 transition-all duration-150 shrink-0"
          >
            {sending ? "…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
