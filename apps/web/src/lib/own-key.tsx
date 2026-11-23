"use client";
// The user's own OpenRouter key (BYOK, T-503): kept only in the memory of this tab — no
// localStorage, no cookie, no URL. It goes with a run's start and with every answer.
import { createContext, useContext, useState, type ReactNode } from "react";

// `asking` opens the key dialog of the header: the demo limit screen offers it (T-512).
type OwnKey = { key: string; setKey: (key: string) => void; asking: boolean; ask: (open: boolean) => void };

const Context = createContext<OwnKey>({ key: "", setKey: () => {}, asking: false, ask: () => {} });

export function OwnKeyProvider({ children }: { children: ReactNode }) {
  const [key, setKey] = useState("");
  const [asking, ask] = useState(false);
  return <Context.Provider value={{ key, setKey, asking, ask }}>{children}</Context.Provider>;
}

export function useOwnKey(): OwnKey {
  return useContext(Context);
}
