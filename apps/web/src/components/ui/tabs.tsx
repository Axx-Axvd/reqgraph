"use client";
// Tabs inside a page (T-511): role tablist, the arrow keys move between tabs, one panel is shown.
import { useId, useRef, type ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Tabs<T extends string>({
  label,
  tabs,
  value,
  onChange,
  children,
}: {
  label: string;
  tabs: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  children: ReactNode;
}) {
  const base = useId();
  const list = useRef<HTMLDivElement>(null);
  function onKey(event: React.KeyboardEvent, index: number) {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = tabs[(index + step + tabs.length) % tabs.length];
    onChange(next.value);
    list.current?.querySelector<HTMLButtonElement>(`[data-value="${next.value}"]`)?.focus();
  }
  return (
    <div className="flex flex-col gap-4">
      <div ref={list} role="tablist" aria-label={label} className="flex gap-1 overflow-x-auto border-b border-line">
        {tabs.map((t, i) => (
          <button
            key={t.value}
            type="button"
            role="tab"
            id={`${base}-${t.value}`}
            data-value={t.value}
            aria-selected={value === t.value}
            aria-controls={`${base}-panel`}
            tabIndex={value === t.value ? 0 : -1}
            onClick={() => onChange(t.value)}
            onKeyDown={(e) => onKey(e, i)}
            className={cn(
              "-mb-px min-h-11 shrink-0 border-b-2 border-transparent px-4 text-[15px] text-muted hover:text-fg",
              value === t.value && "border-coral font-medium text-fg",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${base}-panel`} aria-labelledby={`${base}-${value}`}>
        {children}
      </div>
    </div>
  );
}
