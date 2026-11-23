"use client";
// The start of the landing page (T-509): «Чем вы занимаетесь?» → the text waits in sessionStorage across the
// sign-in, and the new project starts from it (projects page). Quiet examples fill the field.
import { ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { START_KEY } from "@/lib/example";

const EXAMPLES: [string, string][] = [
  ["автосервис", "Автосервис, 4 мастера, клиенты записываются по телефону"],
  ["стоматология", "Стоматология, 3 кресла, запись по телефону"],
  ["пекарня", "Пекарня, торты на заказ по телефону и в мессенджере"],
];

export function StartForm() {
  const router = useRouter();
  const [text, setText] = useState("");

  function start(e: FormEvent) {
    e.preventDefault();
    const value = text.trim();
    if (!value) return;
    try {
      sessionStorage.setItem(START_KEY, value);
    } catch {
      // private mode: the visitor types it again in the project form
    }
    router.push("/projects");
  }

  return (
    <form onSubmit={start} className="flex max-w-[580px] flex-col gap-3">
      <label htmlFor="start" className="sr-only">
        Чем вы занимаетесь?
      </label>
      <div className="flex items-center gap-2 rounded-[18px] border border-line-2 bg-surface py-2 pr-2 pl-4 transition-[border-color,box-shadow] focus-within:border-coral focus-within:shadow-[0_0_0_4px_var(--coral-tint)] max-sm:flex-col max-sm:items-stretch max-sm:pl-2">
        <input
          id="start"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Чем вы занимаетесь?"
          autoComplete="off"
          className="min-w-0 flex-1 !border-0 !bg-transparent !shadow-none !outline-none max-sm:!px-2"
        />
        <Button type="submit" size="lg" disabled={!text.trim()}>
          Начать
          <ArrowRight aria-hidden="true" />
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-1 pl-4 text-[13px] max-sm:pl-0">
        <span className="text-dim">Например:</span>
        {EXAMPLES.map(([label, value]) => (
          <button
            key={label}
            type="button"
            onClick={() => setText(value)}
            className="min-h-8 rounded-lg px-1.5 text-muted underline decoration-line-2 underline-offset-[3px] hover:text-fg"
          >
            {label}
          </button>
        ))}
      </div>
    </form>
  );
}
