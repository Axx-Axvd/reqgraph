// Something went wrong (T-512): what happened, what is kept, what to do — and the button to do it.
import { CloudOff, Hourglass, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const ICONS = { limit: Hourglass, offline: CloudOff, error: TriangleAlert };

export function Problem({
  kind = "error",
  title,
  children,
  actions,
  className,
}: {
  kind?: keyof typeof ICONS;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  const Icon = ICONS[kind];
  return (
    <div
      role="alert"
      data-testid="problem"
      className={cn(
        "flex gap-3 rounded-panel border border-[color-mix(in_srgb,var(--amber)_45%,transparent)] bg-amber-fill/40 p-4",
        className,
      )}
    >
      <Icon aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-amber" />
      <div className="flex min-w-0 flex-col gap-2">
        <p className="m-0 font-medium text-fg">{title}</p>
        {children && <div className="m-0 text-sm text-muted">{children}</div>}
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
    </div>
  );
}

export const OFFLINE = "Нет связи с сервером. Проверьте интернет и попробуйте ещё раз.";
