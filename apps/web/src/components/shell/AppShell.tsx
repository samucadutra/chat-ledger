import Link from "next/link";
import type { ReactNode } from "react";
import { ApiStatusBanner } from "@/components/system/ApiStatusBanner";
import { HeaderBar } from "./HeaderBar";
import { SideNav } from "./SideNav";

export interface AppShellProps {
  children: ReactNode;
  /** Header slot showing the current matter. */
  currentMatter?: ReactNode;
}

/** Application frame: API status banner, left navigation, header and main region. */
export function AppShell({ children, currentMatter }: AppShellProps) {
  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <ApiStatusBanner />
      <div className="flex min-h-0 flex-1">
        <aside className="flex w-[var(--cl-sidebar-width)] shrink-0 flex-col overflow-y-auto border-r border-rule bg-paper-sunken">
          <Link
            href="/matters"
            className="flex h-[var(--cl-header-height)] items-center gap-2.5 border-b border-rule px-6"
          >
            <span aria-hidden className="grid h-6 w-6 place-items-center rounded-sm bg-accent font-mono text-[12px] font-semibold text-accent-ink">
              CL
            </span>
            <span className="text-[15px] font-semibold tracking-[-0.01em]">ChatLedger</span>
          </Link>
          <SideNav />
          <div className="mt-auto border-t border-rule px-6 py-4">
            <p className="cl-label">Slack → RSMF</p>
            <p className="mt-1 text-[12px] leading-4 text-ink-faint">Defensible, reproducible evidence runs.</p>
          </div>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col overflow-y-auto">
          <HeaderBar currentMatter={currentMatter} />
          <main id="main" className="flex-1 px-8 py-8">
            <div className="mx-auto w-full max-w-5xl">{children}</div>
          </main>
        </div>
      </div>
    </div>
  );
}
