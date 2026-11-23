"use client";
// «Посмотреть пример готового ТЗ»: a page of section 4 of the example ТЗ, every item with the words it came from.
import { FileText } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { EXAMPLE_NAME, EXAMPLE_TZ } from "@/lib/example";

export function ExampleDialog() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="secondary" className="h-auto max-w-full py-2.5 whitespace-normal">
          <FileText aria-hidden="true" />
          Посмотреть пример готового ТЗ
        </Button>
      </DialogTrigger>
      <DialogContent title="Пример готового ТЗ" description={`Пример условный: ${EXAMPLE_NAME}.`} className="max-w-[760px]">
        <article className="rounded-lg bg-paper px-6 py-8 font-serif text-[16px] leading-relaxed text-paper-fg sm:px-10">
          <p className="m-0 mb-1 font-sans text-xs tracking-[0.08em] text-[#55596a]">ТЕХНИЧЕСКОЕ ЗАДАНИЕ · ГОСТ 34.602-2020</p>
          <h3 className="m-0 mb-5 text-2xl font-bold">4. Требования к системе</h3>
          <ol className="m-0 flex list-none flex-col gap-4 p-0">
            {EXAMPLE_TZ.map((item) => (
              <li key={item.id} className="flex flex-col gap-1.5">
                <span>{item.spec}</span>
                <span className="font-sans text-[13px] text-[#a8401c]">из ответа: «{item.said}»</span>
              </li>
            ))}
          </ol>
        </article>
        <Button asChild size="lg" className="self-center">
          <Link href="/login">Сделать такое же для своего дела</Link>
        </Button>
      </DialogContent>
    </Dialog>
  );
}
