import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Toast = { id: number; title: string; body?: string };
const ToastContext = createContext<(title: string, body?: string) => void>(() => {});

/** Toasts are styled as determination slips pinned to the corner of the cabinet. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((title: string, body?: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-2), { id, title, body }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="toast det-slip">
            <div className="label">Det. recorded</div>
            <div className="toast-title">{t.title}</div>
            {t.body && <div className="caption">{t.body}</div>}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
