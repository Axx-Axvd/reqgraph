// A panel: the surface of «Сигнал» with a thin line and the panel radius.
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export function Card({ className, ...props }: ComponentProps<"section">) {
  return (
    <section
      className={cn("rounded-panel border border-line bg-surface p-5", className)}
      {...props}
    />
  );
}
