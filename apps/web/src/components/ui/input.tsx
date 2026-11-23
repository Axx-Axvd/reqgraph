// A text field: the coral ring on focus is the focus indicator of the field (board «Компоненты»).
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn("w-full", className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn("w-full resize-y", className)} {...props} />;
}
