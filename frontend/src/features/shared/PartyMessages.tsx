import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import {
  ContactThread,
  Message,
  fetchChatWith,
  fetchMyContacts,
  fetchMyThread,
  fetchMyUnreadCount,
  sendChatMessage,
  sendMyMessage,
} from "../../api/messages";
import ChatThread from "./ChatThread";
import { Skeleton, SkeletonChat } from "./ui/Skeleton";

const CONTACTS_POLL_MS = 8000;
const MESSAGES_POLL_MS = 4000;

// "admin" = the chat with SPAR Admin; a number = a branch (for a supplier)
// or a supplier (for a branch).
type Selection = "admin" | number;

function relativeTime(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.round(hrs / 24)}d`;
}

function UnreadDot({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="shrink-0 inline-flex items-center justify-center min-w-[1.1rem] h-[1.1rem] px-1 rounded-full bg-tomato-500 text-white text-[10px] font-bold">
      {count > 99 ? "99+" : count}
    </span>
  );
}

/**
 * Messages for a supplier or a branch: their chat with SPAR Admin, plus a
 * direct chat with each branch (for a supplier) or each supplier (for a
 * branch). SPAR Admin can read the direct chats.
 */
export default function PartyMessages({ role }: { role: "SUPPLIER" | "BRANCH" }) {
  const contactsLabel = role === "SUPPLIER" ? "Branches" : "Suppliers";
  const [contacts, setContacts] = useState<ContactThread[]>([]);
  const [adminUnread, setAdminUnread] = useState(0);
  const [contactsLoading, setContactsLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Selection>("admin");
  // Phones show the list or the chat, not both.
  const [showChatOnMobile, setShowChatOnMobile] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const messagesPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadContacts = useCallback(() => {
    return Promise.all([fetchMyContacts(), fetchMyUnreadCount()])
      .then(([list, total]) => {
        setContacts(list);
        // The total badge covers every chat; what's left over is Admin's.
        const fromContacts = list.reduce((sum, c) => sum + c.unread_count, 0);
        setAdminUnread(Math.max(0, total.count - fromContacts));
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    setContactsLoading(true);
    loadContacts().finally(() => setContactsLoading(false));
    const id = setInterval(loadContacts, CONTACTS_POLL_MS);
    return () => clearInterval(id);
  }, [loadContacts]);

  const loadMessages = useCallback((sel: Selection) => {
    const fetcher = sel === "admin" ? fetchMyThread() : fetchChatWith(sel);
    return fetcher
      .then((data) => {
        setMessages(data);
        setError(null);
        // Opening a chat marks it read server-side — clear its badge now.
        if (sel === "admin") setAdminUnread(0);
        else setContacts((prev) => prev.map((c) => (c.id === sel ? { ...c, unread_count: 0 } : c)));
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load messages."));
  }, []);

  useEffect(() => {
    if (messagesPollRef.current) clearInterval(messagesPollRef.current);
    setMessages([]);
    setMessagesLoading(true);
    loadMessages(selected).finally(() => setMessagesLoading(false));
    messagesPollRef.current = setInterval(() => loadMessages(selected), MESSAGES_POLL_MS);
    return () => {
      if (messagesPollRef.current) clearInterval(messagesPollRef.current);
    };
  }, [selected, loadMessages]);

  async function handleSend(body: string) {
    const sent = selected === "admin" ? await sendMyMessage(body) : await sendChatMessage(selected, body);
    setMessages((prev) => [...prev, sent]);
    if (selected !== "admin") {
      setContacts((prev) =>
        prev.map((c) => (c.id === selected ? { ...c, last_message_body: body, last_message_at: sent.created_at } : c))
      );
    }
  }

  function choose(sel: Selection) {
    setSelected(sel);
    setShowChatOnMobile(true);
  }

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? contacts.filter((c) => c.name.toLowerCase().includes(q) || c.code.toLowerCase().includes(q)) : contacts;
  }, [contacts, search]);

  const contact = selected === "admin" ? null : contacts.find((c) => c.id === selected) ?? null;
  const title = selected === "admin" ? "SPAR Admin" : contact?.name ?? "";

  const rowClass = (active: boolean) =>
    `w-full text-left px-4 py-3 border-b border-sage-50 transition-colors duration-150 ${
      active ? "bg-sage-100" : "hover:bg-sage-50"
    }`;

  return (
    <div
      className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 overflow-hidden flex"
      style={{ height: "36rem" }}
    >
      <div
        className={`${showChatOnMobile ? "hidden" : "flex"} md:flex w-full md:w-64 shrink-0 md:border-r border-sage-100 flex-col min-h-0`}
      >
        <button onClick={() => choose("admin")} className={rowClass(selected === "admin")}>
          <div className="flex items-center justify-between gap-2">
            <span className={`text-sm ${selected === "admin" ? "font-semibold text-crate-950" : "text-crate-800"}`}>
              SPAR Admin
            </span>
            <UnreadDot count={adminUnread} />
          </div>
          <p className="text-xs text-crate-800/40 mt-0.5">Procurement team</p>
        </button>

        <div className="px-3 pt-3 pb-2 border-b border-sage-100 shrink-0">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-crate-800/50 mb-1.5 px-1">{contactsLabel}</p>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={`Find a ${role === "SUPPLIER" ? "branch" : "supplier"}…`}
            className="w-full border border-sage-300 bg-sage-50/60 rounded-full px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white"
          />
        </div>

        <div className="overflow-y-auto flex-1 min-h-0">
          {contactsLoading ? (
            <div className="p-3 space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="space-y-1.5 px-1">
                  <Skeleton className="h-3.5 w-2/3" />
                  <Skeleton className="h-3 w-4/5" />
                </div>
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-crate-800/40 text-center py-6 px-3">No {contactsLabel.toLowerCase()} found.</p>
          ) : (
            filtered.map((c) => {
              const active = c.id === selected;
              return (
                <button key={c.id} onClick={() => choose(c.id)} className={rowClass(active)}>
                  <div className="flex items-center justify-between gap-2">
                    <span className={`text-sm truncate ${active ? "font-semibold text-crate-950" : "text-crate-800"}`}>
                      {c.name}
                    </span>
                    <UnreadDot count={c.unread_count} />
                  </div>
                  <p className="text-xs text-crate-800/40 truncate mt-0.5">
                    {c.last_message_body ?? "No messages yet"}
                    {c.last_message_at && <span className="ml-1.5 text-crate-800/30">· {relativeTime(c.last_message_at)}</span>}
                  </p>
                </button>
              );
            })
          )}
        </div>
      </div>

      <div className={`${showChatOnMobile ? "flex" : "hidden"} md:flex flex-1 flex-col min-h-0 min-w-0`}>
        <div className="px-4 py-3 border-b border-sage-100 shrink-0 flex items-center gap-3">
          <button
            onClick={() => setShowChatOnMobile(false)}
            className="md:hidden text-sm font-semibold text-crate-700"
            aria-label="Back to conversations"
          >
            ←
          </button>
          <div className="min-w-0">
            <p className="font-display font-semibold text-sm text-crate-950 truncate">{title}</p>
            {selected !== "admin" && (
              <p className="text-[11px] text-crate-800/40">SPAR Admin can also see this conversation.</p>
            )}
          </div>
        </div>
        {messagesLoading ? (
          <SkeletonChat />
        ) : error ? (
          <p className="text-tomato-600 text-sm p-4">{error}</p>
        ) : (
          <div className="flex-1 min-h-0">
            <ChatThread
              messages={messages}
              currentRole={role}
              onSend={handleSend}
              emptyHint={`No messages with ${title} yet — say hello below.`}
            />
          </div>
        )}
      </div>
    </div>
  );
}
