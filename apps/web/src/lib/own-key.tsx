"use client";
// The user's own OpenRouter key (BYOK, T-503): kept only in the memory of this tab — no
// localStorage, no cookie, no URL. It goes with a run's start and with every answer.
import { createContext, useContext, useState, type ReactNode } from "react";

type OwnKey = { key: string; setKey: (key: string) => void };

const Context = createContext<OwnKey>({ key: "", setKey: () => {} });

export function OwnKeyProvider({ children }: { children: ReactNode }) {
  const [key, setKey] = useState("");
  return <Context.Provider value={{ key, setKey }}>{children}</Context.Provider>;
}

export function useOwnKey(): OwnKey {
  return useContext(Context);
}
