"use client";

import * as RadixToast from "@radix-ui/react-toast";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export type ToastTone = "neutral" | "success" | "error";

export interface ToastOptions {
  title: string;
  description?: string;
  tone?: ToastTone;
  durationMs?: number;
}

interface ToastItem extends ToastOptions {
  id: number;
}

interface ToastApi {
  toast: (options: ToastOptions) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const toneRule: Record<ToastTone, string> = {
  neutral: "before:bg-ink-faint",
  success: "before:bg-ink",
  error: "before:bg-accent",
};

/** Mount once (in `Providers`); exposes `useToast()` to every component. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const toast = useCallback((options: ToastOptions) => {
    setItems((prev) => [...prev, { ...options, id: Date.now() + Math.random() }]);
  }, []);

  const remove = useCallback((id: number) => {
    setItems((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const api = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={api}>
      <RadixToast.Provider swipeDirection="right">
        {children}
        {items.map((item) => (
          <RadixToast.Root
            key={item.id}
            duration={item.durationMs ?? 5000}
            onOpenChange={(open) => {
              if (!open) remove(item.id);
            }}
            className={cn(
              "relative grid gap-1 border border-rule-strong bg-paper-raised py-3 pl-5 pr-10 shadow-[var(--cl-shadow-pop)]",
              "before:absolute before:inset-y-0 before:left-0 before:w-[3px]",
              "data-[state=open]:animate-[cl-slide-in_160ms_ease-out]",
              toneRule[item.tone ?? "neutral"],
            )}
          >
            <RadixToast.Title className="text-[13px] font-semibold">{item.title}</RadixToast.Title>
            {item.description ? (
              <RadixToast.Description className="text-[13px] text-ink-muted">
                {item.description}
              </RadixToast.Description>
            ) : null}
            <RadixToast.Close
              aria-label="Dismiss"
              className="absolute right-2 top-2 h-7 w-7 rounded-sm text-ink-faint hover:bg-paper-sunken hover:text-ink"
            >
              ×
            </RadixToast.Close>
          </RadixToast.Root>
        ))}
        <RadixToast.Viewport className="fixed bottom-4 right-4 z-[60] flex w-[360px] max-w-[calc(100vw-32px)] flex-col gap-2 outline-none" />
      </RadixToast.Provider>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
