import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { Message, fetchMyThread, sendMyMessage } from "../../api/messages";
import ChatThread from "../shared/ChatThread";
import { SkeletonChat } from "../shared/ui/Skeleton";

const POLL_MS = 4000;

export default function BranchMessages() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(() => {
    return fetchMyThread()
      .then((data) => {
        setMessages(data);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Could not load messages.");
      });
  }, []);

  useEffect(() => {
    setLoading(true);
    load().finally(() => setLoading(false));
    pollRef.current = setInterval(load, POLL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [load]);

  async function handleSend(body: string) {
    const sent = await sendMyMessage(body);
    setMessages((prev) => [...prev, sent]);
  }

  return (
    <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 overflow-hidden flex flex-col" style={{ height: "32rem" }}>
      <div className="px-4 py-3 border-b border-sage-100 shrink-0">
        <p className="font-display font-semibold text-sm text-crate-950">Messages with Admin</p>
      </div>
      {loading ? (
        <SkeletonChat />
      ) : error ? (
        <p className="text-tomato-600 text-sm p-4">{error}</p>
      ) : (
        <div className="flex-1 min-h-0">
          <ChatThread
            messages={messages}
            currentRole="BRANCH"
            onSend={handleSend}
            emptyHint="No messages yet — say hello to Admin below."
          />
        </div>
      )}
    </div>
  );
}
