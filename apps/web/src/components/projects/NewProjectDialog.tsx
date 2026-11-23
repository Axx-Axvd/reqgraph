"use client";
// «Новый проект» (T-510, board «Проекты и новый проект»): one field «Чем вы занимаетесь?». The name is the
// first clause of the text, the whole text is the brief. What the visitor typed on the landing page opens
// the dialog already filled in.
import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { api, errorText } from "@/lib/api";
import { START_KEY } from "@/lib/example";

/** The project name: the first clause of what the person wrote (the API needs a name). */
export function nameOf(text: string): string {
  const first = text.split(/[,.;:\n—]/)[0].trim();
  return (first || text.trim()).slice(0, 80) || "Новый проект";
}

function landingText(): string {
  try {
    return (typeof window === "undefined" ? null : sessionStorage.getItem(START_KEY)) ?? "";
  } catch {
    return "";
  }
}

export function NewProjectDialog({ trigger, autoOpen = false }: { trigger?: ReactNode; autoOpen?: boolean }) {
  const router = useRouter();
  const [text, setText] = useState(landingText);
  const [open, setOpen] = useState(() => autoOpen && landingText() !== "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function create(e: FormEvent) {
    e.preventDefault();
    const brief = text.trim();
    if (!brief || busy) return;
    setBusy(true);
    setError("");
    const { data, error } = await api().POST("/projects", { body: { name: nameOf(brief), brief } });
    setBusy(false);
    if (error || !data) {
      setError(errorText(error));
      return;
    }
    try {
      sessionStorage.removeItem(START_KEY);
    } catch {
      // nothing kept
    }
    router.push(`/projects/${data.id}`);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button>
            <Plus aria-hidden="true" />
            Новый проект
          </Button>
        )}
      </DialogTrigger>
      <DialogContent title="Новый проект" description="Пары слов достаточно — остальное спросит аналитик.">
        <form onSubmit={create} className="flex flex-col gap-4">
          <label>
            Чем вы занимаетесь?
            <textarea
              rows={4}
              required
              maxLength={4000}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Например: две пекарни, заказы тортов по телефону и в мессенджере"
            />
          </label>
          {error && (
            <p className="error m-0" role="alert">
              {error}
            </p>
          )}
          <Button type="submit" size="lg" className="self-end" disabled={busy || !text.trim()}>
            {busy ? "Создаём…" : "Создать проект"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
