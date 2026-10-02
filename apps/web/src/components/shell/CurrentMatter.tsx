"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

interface CurrentMatterApi {
  name: string | null;
  setName: (name: string | null) => void;
}

const CurrentMatterContext = createContext<CurrentMatterApi>({ name: null, setName: () => {} });

/** Holds the name of the matter being viewed so the header bar can show it. */
export function CurrentMatterProvider({ children }: { children: ReactNode }) {
  const [name, setName] = useState<string | null>(null);
  const value = useMemo(() => ({ name, setName }), [name]);
  return <CurrentMatterContext.Provider value={value}>{children}</CurrentMatterContext.Provider>;
}

export function useCurrentMatterName(): string | null {
  return useContext(CurrentMatterContext).name;
}

/** Publish `name` as the current matter while the calling component is mounted. */
export function usePublishCurrentMatter(name: string | null): void {
  const { setName } = useContext(CurrentMatterContext);
  useEffect(() => {
    setName(name);
    return () => setName(null);
  }, [name, setName]);
}
