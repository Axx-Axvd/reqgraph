// The mark of reqgraph: a coral point (the person) joined by a thread to a mint point (checked).
export function Logo({ withName = true }: { withName?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5 font-display text-[15px] font-bold tracking-tight">
      <svg width="24" height="24" viewBox="0 0 26 26" aria-hidden="true">
        <circle cx="6" cy="7" r="3.5" fill="var(--coral)" />
        <circle cx="20" cy="19" r="3.5" fill="var(--mint)" />
        <path d="M8.5 9.5 C 12 14, 14 12, 17.5 16.5" fill="none" stroke="var(--fg)" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
      {withName && <span className="max-sm:sr-only">reqgraph</span>}
    </span>
  );
}
