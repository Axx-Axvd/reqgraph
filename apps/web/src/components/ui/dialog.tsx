"use client";
// A dialog on Radix: focus moves inside, Tab stays inside, Escape and the backdrop close it,
// focus returns to the button that opened it.
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({
  className,
  children,
  title,
  description,
  ...props
}: ComponentProps<typeof DialogPrimitive.Content> & { title: string; description?: string }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-(--backdrop) data-[state=open]:animate-in data-[state=open]:fade-in-0" />
      <DialogPrimitive.Content
        className={cn(
          "fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-32px)] w-[calc(100vw-32px)] max-w-[560px] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 overflow-y-auto rounded-3xl border border-line-2 bg-surface p-6 shadow-(--shadow) data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
          className,
        )}
        {...props}
      >
        <div className="flex items-start gap-3">
          <DialogPrimitive.Title className="m-0 font-display text-xl font-bold tracking-tight">{title}</DialogPrimitive.Title>
          <DialogPrimitive.Close
            aria-label="Закрыть"
            className="ml-auto inline-flex size-11 shrink-0 items-center justify-center rounded-xl text-muted hover:bg-raised"
          >
            <X aria-hidden="true" />
          </DialogPrimitive.Close>
        </div>
        {description ? (
          <DialogPrimitive.Description className="m-0 text-sm text-muted">{description}</DialogPrimitive.Description>
        ) : (
          <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
        )}
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}
