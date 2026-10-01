"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";

export const NAV_ITEMS = [
  { href: "/matters", label: "Matters", hint: "Collections & runs" },
  { href: "/reason-codes", label: "Reason Codes", hint: "Exclusion catalogue" },
] as const;

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function SideNav() {
  const pathname = usePathname() ?? "/";
  return (
    <nav aria-label="Primary" className="flex flex-col gap-px px-3 py-4">
      <span className="cl-label px-3 pb-2">Workspace</span>
      {NAV_ITEMS.map((item) => {
        const active = isActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group relative flex flex-col rounded-sm px-3 py-2 transition-colors duration-100",
              "before:absolute before:inset-y-1.5 before:left-0 before:w-[2px] before:rounded-full",
              active
                ? "bg-paper-raised text-ink before:bg-accent"
                : "text-ink-muted hover:bg-paper-raised/60 hover:text-ink before:bg-transparent",
            )}
          >
            <span className="text-[14px] font-medium leading-5">{item.label}</span>
            <span className="font-mono text-[11px] leading-4 text-ink-faint">{item.hint}</span>
          </Link>
        );
      })}
    </nav>
  );
}
