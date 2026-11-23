// Placeholders while data loads instead of «Загружаем…» text; the text stays for screen readers.
import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <span aria-hidden="true" className={cn("block animate-pulse rounded-lg bg-raised", className)} />;
}

export function Loading({ label = "Загружаем…", lines = 3 }: { label?: string; lines?: number }) {
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-3 py-2">
      <span className="sr-only">{label}</span>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={cn("h-4", i === lines - 1 ? "w-2/5" : i % 2 ? "w-3/4" : "w-11/12")} />
      ))}
    </div>
  );
}
