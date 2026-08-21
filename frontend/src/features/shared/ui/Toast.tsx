import { createContext, ReactNode, useCallback, useContext, useRef, useState } from "react";
import { createPortal } from "react-dom";

type ToastType = "success" | "error" | "warning" | "info";
type Toast = { id: number; type: ToastType; message: string };

const ToastContext = createContext<{ show: (type: ToastType, message: string) => void } | null>(null);

const toneClasses: Record<ToastType, string> = {
  success: "border-crate-700/20 bg-white text-crate-800",
  error: "border-tomato-500/30 bg-white text-tomato-600",
  warning: "border-mango-500/30 bg-white text-[#8A5A0D]",
  info: "border-sage-300 bg-white text-crate-800",
};

const dotClasses: Record<ToastType, string> = {
  success: "bg-crate-700",
  error: "bg-tomato-500",
  warning: "bg-mango-500",
  info: "bg-crate-700/50",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const show = useCallback((type: ToastType, message: string) => {
    const id = nextId.current++;
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      {createPortal(
        <div className="fixed bottom-5 right-5 z-[60] flex flex-col gap-2 w-80 max-w-[calc(100vw-2.5rem)]">
          {toasts.map((t) => (
            <div
              key={t.id}
              role="status"
              className={`flex items-start gap-2.5 rounded-xl border shadow-dropdown px-4 py-3 text-sm animate-fade-up ${toneClasses[t.type]}`}
              style={{ animationDuration: "0.25s" }}
            >
              <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${dotClasses[t.type]}`} aria-hidden="true" />
              {t.message}
            </div>
          ))}
        </div>,
        document.body
      )}
    </ToastContext.Provider>
  );
}

/** useToast().show("success" | "error" | "warning" | "info", "message") */
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
