import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import {
  Message,
  fetchAdminThread,
  fetchAdminThreads,
  fetchAdminBranchThread,
  fetchAdminBranchThreads,
  sendAdminMessage,
  sendAdminBranchMessage,
} from "../../api/messages";
import ChatThread from "../shared/ChatThread";
import { Skeleton, SkeletonChat } from "../shared/ui/Skeleton";
import { IconChat } from "../shared/Icons";

const THREADS_POLL_MS = 8000;
const MESSAGES_POLL_MS = 4000;

type PartyType = "SUPPLIER" | "BRANCH";

// Supplier and Branch threads are the same shape apart from the id/code/name
// field names — normalized here so the list/detail UI below doesn't need to
// branch on party type at all, only the fetch/send calls do.
type Thread = {
  id: number;
  code: string;
  name: string;
  last_message_body: string | null;
  last_message_at: string | null;
  unread_count: number;
};

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.round(hrs / 24)}d`;
}

export default function AdminMessages() {
  const [partyType, setPartyType] = useState<PartyType>("SUPPLIER");
  const [threads, setThreads] = useState<Thread[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const threadsPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const messagesPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadThreads = useCallback(() => {
    const fetcher = partyType === "SUPPLIER" ? fetchAdminThreads : fetchAdminBranchThreads;
    return fetcher()
      .then((data) => {
        const normalized: Thread[] =
          partyType === "SUPPLIER"
            ? (data as Awaited<ReturnType<typeof fetchAdminThreads>>).map((t) => ({
                id: t.supplier_id,
                code: t.supplier_code,
                name: t.supplier_name,
                last_message_body: t.last_message_body,
                last_message_at: t.last_message_at,
                unread_count: t.unread_count,
              }))
            : (data as Awaited<ReturnType<typeof fetchAdminBranchThreads>>).map((t) => ({
                id: t.branch_id,
                code: t.branch_code,
                name: t.branch_name,
                last_message_body: t.last_message_body,
                last_message_at: t.last_message_at,
                unread_count: t.unread_count,
              }));
        setThreads(normalized);
        setSelectedId((prev) => prev ?? (normalized.length > 0 ? normalized[0].id : null));
      })
      .catch(() => {});
  }, [partyType]);

  // Switching between Suppliers/Branches starts a fresh list — the
  // previously selected id belongs to the other party type.
  useEffect(() => {
    setSelectedId(null);
    setMessages([]);
  }, [partyType]);

  useEffect(() => {
    setThreadsLoading(true);
    loadThreads().finally(() => setThreadsLoading(false));
    threadsPollRef.current = setInterval(loadThreads, THREADS_POLL_MS);
    return () => {
      if (threadsPollRef.current) clearInterval(threadsPollRef.current);
    };
  }, [loadThreads]);

  const loadMessages = useCallback(
    (id: number) => {
      const fetcher = partyType === "SUPPLIER" ? fetchAdminThread : fetchAdminBranchThread;
      return fetcher(id)
        .then((data) => {
          setMessages(data);
          setError(null);
          // Opening/refreshing a thread marks it read server-side — reflect
          // that locally right away so the sidebar badge clears instantly.
          setThreads((prev) => prev.map((t) => (t.id === id ? { ...t, unread_count: 0 } : t)));
        })
        .catch((err) => {
          setError(err instanceof ApiError ? err.message : "Could not load this conversation.");
        });
    },
    [partyType]
  );

  useEffect(() => {
    if (messagesPollRef.current) clearInterval(messagesPollRef.current);
    if (selectedId === null) {
      setMessages([]);
      return;
    }
    setMessagesLoading(true);
    loadMessages(selectedId).finally(() => setMessagesLoading(false));
    messagesPollRef.current = setInterval(() => loadMessages(selectedId), MESSAGES_POLL_MS);
    return () => {
      if (messagesPollRef.current) clearInterval(messagesPollRef.current);
    };
  }, [selectedId, loadMessages]);

  async function handleSend(body: string) {
    if (selectedId === null) return;
    const sent =
      partyType === "SUPPLIER"
        ? await sendAdminMessage(selectedId, body)
        : await sendAdminBranchMessage(selectedId, body);
    setMessages((prev) => [...prev, sent]);
    setThreads((prev) =>
      prev.map((t) => (t.id === selectedId ? { ...t, last_message_body: body, last_message_at: sent.created_at } : t))
    );
  }

  const selected = threads.find((t) => t.id === selectedId) ?? null;
  const partyLabel = partyType === "SUPPLIER" ? "supplier" : "branch";

  return (
    <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 overflow-hidden flex" style={{ height: "36rem" }}>
      <div className="w-64 shrink-0 border-r border-sage-100 overflow-y-auto flex flex-col">
        <div className="px-3 pt-3 pb-2 border-b border-sage-100 shrink-0">
          <div className="grid grid-cols-2 gap-1 bg-sage-100 rounded-full p-0.5">
            {(["SUPPLIER", "BRANCH"] as PartyType[]).map((pt) => (
              <button
                key={pt}
                onClick={() => setPartyType(pt)}
                className={`text-xs font-semibold rounded-full py-1.5 transition-colors duration-150 ${
                  partyType === pt ? "bg-white text-crate-950 shadow-sm" : "text-crate-800/50 hover:text-crate-800"
                }`}
              >
                {pt === "SUPPLIER" ? "Suppliers" : "Branches"}
              </button>
            ))}
          </div>
        </div>
        {threadsLoading ? (
          <div className="p-3 space-y-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="space-y-1.5 px-1">
                <Skeleton className="h-3.5 w-2/3" />
                <Skeleton className="h-3 w-4/5" />
              </div>
            ))}
          </div>
        ) : threads.length === 0 ? (
          <p className="text-sm text-crate-800/40 text-center py-8 px-3">No active {partyLabel}s yet.</p>
        ) : (
          <div className="overflow-y-auto">
            {threads.map((t) => {
              const isActive = t.id === selectedId;
              return (
                <button
                  key={t.id}
                  onClick={() => setSelectedId(t.id)}
                  className={`w-full text-left px-4 py-3 border-b border-sage-50 transition-colors duration-150 ${
                    isActive ? "bg-sage-100" : "hover:bg-sage-50"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className={`text-sm truncate ${isActive ? "font-semibold text-crate-950" : "text-crate-800"}`}>
                      {t.name}
                    </span>
                    {t.unread_count > 0 && (
                      <span className="shrink-0 inline-flex items-center justify-center min-w-[1.1rem] h-[1.1rem] px-1 rounded-full bg-tomato-500 text-white text-[10px] font-bold">
                        {t.unread_count > 99 ? "99+" : t.unread_count}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-crate-800/40 truncate mt-0.5">
                    {t.last_message_body ?? "No messages yet"}
                    {t.last_message_at && <span className="ml-1.5 text-crate-800/30">· {relativeTime(t.last_message_at)}</span>}
                  </p>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="flex-1 flex flex-col min-h-0">
        {!selected ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 text-crate-800/35">
            <IconChat width={28} height={28} />
            <p className="text-sm">Pick a {partyLabel} to start chatting.</p>
          </div>
        ) : (
          <>
            <div className="px-4 py-3 border-b border-sage-100 shrink-0">
              <p className="font-display font-semibold text-sm text-crate-950">{selected.name}</p>
            </div>
            {messagesLoading ? (
              <SkeletonChat />
            ) : error ? (
              <p className="text-tomato-600 text-sm p-4">{error}</p>
            ) : (
              <div className="flex-1 min-h-0">
                <ChatThread
                  messages={messages}
                  currentRole="ADMIN"
                  onSend={handleSend}
                  emptyHint={`No messages with ${selected.name} yet.`}
                />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
