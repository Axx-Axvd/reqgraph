// A state label: coral — in progress, mint — done, amber — to clarify, neutral — draft.
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs", {
  variants: {
    tone: {
      neutral: "bg-raised text-muted",
      coral: "bg-coral-tint text-coral-text",
      mint: "bg-mint-fill text-mint-text",
      amber: "bg-amber-fill text-amber-text",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export function Badge({ className, tone, ...props }: ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
