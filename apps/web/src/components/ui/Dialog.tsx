"use client";

import * as RadixDialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

export interface DialogProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  trigger?: ReactNode;
  title: string;
  description?: string;
  children?: ReactNode;
  footer?: ReactNode;
}

/** Token-styled accessible modal dialog (Radix). */
export function Dialog({ open, onOpenChange, trigger, title, description, children, footer }: DialogProps) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger ? <RadixDialog.Trigger asChild>{trigger}</RadixDialog.Trigger> : null}
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-ink/30 backdrop-blur-[1px]" />
        <RadixDialog.Content
          className="fixed left-1/2 top-[12vh] z-50 w-[min(560px,calc(100vw-32px))] -translate-x-1/2 border border-rule-strong bg-paper-raised shadow-[var(--cl-shadow-pop)] focus:outline-none"
        >
          <div className="border-b border-rule px-6 py-4">
            <RadixDialog.Title className="text-[18px] font-semibold leading-tight">{title}</RadixDialog.Title>
            {description ? (
              <RadixDialog.Description className="mt-1 text-[13px] text-ink-muted">
                {description}
              </RadixDialog.Description>
            ) : null}
          </div>
          <div className="px-6 py-5">{children}</div>
          {footer ? (
            <div className="flex justify-end gap-2 border-t border-rule bg-paper px-6 py-3">{footer}</div>
          ) : null}
          <RadixDialog.Close
            aria-label="Close"
            className="absolute right-3 top-3 h-8 w-8 rounded-sm text-ink-faint hover:bg-paper-sunken hover:text-ink"
          >
            ×
          </RadixDialog.Close>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
