// A button of «Сигнал» (board «Компоненты»): one coral button per screen, the rest outline or quiet.
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-control font-[inherit] text-[15px] whitespace-nowrap no-underline transition-[transform,background-color,border-color] duration-200 ease-spring active:scale-[0.96] disabled:pointer-events-none disabled:opacity-60 [&_svg]:size-[18px] [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-coral font-semibold text-on-coral",
        secondary: "border border-line-2 bg-transparent font-medium text-fg hover:bg-raised",
        quiet: "bg-transparent text-muted hover:bg-raised hover:text-fg",
      },
      size: {
        md: "min-h-11 px-[18px]",
        lg: "min-h-[54px] px-6 text-[17px]",
        sm: "min-h-9 px-3 text-sm",
        icon: "size-11",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export type ButtonProps = ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean };

export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

export { buttonVariants };
