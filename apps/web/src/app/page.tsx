// The landing page (T-509, board «Главная»). The worked example is the reference project examples/garage61.
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { Disclaimer } from "@/components/Disclaimer";
import { DemoScene } from "@/components/landing/DemoScene";
import { ExampleDialog } from "@/components/landing/ExampleDialog";
import { StartForm } from "@/components/landing/StartForm";
import { REPO_URL, SiteHeader } from "@/components/SiteHeader";
import { Button } from "@/components/ui/button";
import { EXAMPLE_NAME, PAIRS } from "@/lib/example";

const OUTPUTS = ["ТЗ по ГОСТ", "SRS", "схемы процессов", "модели данных", "сценарии использования", "ReqIF"];

const STEPS = [
  { n: "1", title: "Расскажите", text: "По одному вопросу, своими словами. Аналитик сам спросит, о чём ещё не говорили.", tone: "bg-coral text-on-coral" },
  { n: "2", title: "Проверьте черновик", text: "Требования появляются по ходу разговора — простыми словами, без номеров.", tone: "bg-fg text-bg" },
  { n: "3", title: "Получите ТЗ", text: "ТЗ по ГОСТ со схемами. Каждый пункт проверен кодом и связан с вашими словами.", tone: "bg-mint text-[#16302a]" },
];

export default function Home() {
  return (
    <>
      <SiteHeader />
      <main>
        <section className="mx-auto flex max-w-[1240px] flex-wrap items-center gap-12 px-5 pt-8 pb-20 sm:px-6">
          <div className="sg-lift flex min-w-0 flex-[1_1_480px] flex-col gap-6">
            <h1 className="m-0 font-display hyphens-auto text-[clamp(32px,8.2vw,54px)] leading-[1.04] font-extrabold tracking-[-0.035em]">
              Расскажите о своём деле. <span className="text-coral">Техническое задание</span> мы напишем сами.
            </h1>
            <p className="m-0 max-w-[540px] text-[19px] leading-relaxed text-muted">
              Аналитик спросит, как у вас всё устроено. Из ответов получатся схемы процессов и данных, проверенные кодом, и ТЗ.
            </p>
            <StartForm />
            <p className="m-0 text-sm text-dim">Вход через GitHub или по ссылке на почту</p>
          </div>
          <DemoScene />
        </section>

        <div className="overflow-hidden border-y border-line bg-surface py-4" aria-label="Что получается на выходе">
          <div className="marquee flex w-max gap-10">
            {[...OUTPUTS, ...OUTPUTS].map((o, i) => (
              <span key={i} aria-hidden={i >= OUTPUTS.length} className="inline-flex items-center gap-10 font-display text-lg font-medium whitespace-nowrap text-muted">
                {o}
                <span className="size-1.5 rounded-full bg-coral" />
              </span>
            ))}
          </div>
        </div>

        <section aria-labelledby="say" className="mx-auto flex max-w-[1240px] flex-col gap-7 px-5 pt-20 sm:px-6">
          <h2 id="say" className="m-0 font-display text-[clamp(26px,5vw,40px)] leading-[1.1] font-bold tracking-[-0.03em]">
            Вы говорите как привыкли. В ТЗ — как положено.
          </h2>
          <div className="grid overflow-hidden rounded-3xl border border-line sm:grid-cols-2">
            <span className="bg-surface px-6 pt-5 pb-1 text-[13px] text-muted max-sm:hidden">Как сказал заказчик</span>
            <span className="bg-paper px-8 pt-5 pb-1 text-xs tracking-[0.08em] text-[#55596a] max-sm:hidden">ТЕХНИЧЕСКОЕ ЗАДАНИЕ</span>
            {PAIRS.map((p) => (
              <div key={p.id} className="contents">
                <div className="flex items-center bg-surface px-6 py-4 sm:pr-12">
                  <p className="m-0 rounded-[20px_20px_20px_6px] bg-coral-tint px-4 py-3 text-[15px] leading-normal text-client shadow-[inset_0_0_0_1px_var(--coral-line)]">
                    «{p.said}»
                  </p>
                </div>
                <div className="flex items-center bg-paper px-6 py-4 font-serif text-[16px] leading-relaxed text-paper-fg max-sm:pb-6 sm:px-8">
                  {p.spec}
                </div>
              </div>
            ))}
          </div>
          <p className="m-0 text-[13px] text-dim">Пример условный: {EXAMPLE_NAME} — эталонный проект reqgraph.</p>
        </section>

        <section id="how" aria-labelledby="how-title" className="mx-auto flex max-w-[1240px] scroll-mt-6 flex-col gap-8 px-5 pt-20 sm:px-6">
          <div className="flex flex-wrap items-end gap-5">
            <h2 id="how-title" className="m-0 flex-[1_1_420px] font-display text-[clamp(26px,5vw,38px)] leading-[1.1] font-bold tracking-[-0.03em]">
              Три шага до ТЗ
            </h2>
            <ExampleDialog />
          </div>
          <ol className="m-0 grid list-none gap-4 p-0 md:grid-cols-3">
            {STEPS.map((s) => (
              <li key={s.n} className="flex flex-col gap-3 rounded-[22px] border border-line bg-surface p-6">
                <span className={`inline-flex size-9 items-center justify-center rounded-full font-display font-bold ${s.tone}`} aria-hidden="true">
                  {s.n}
                </span>
                <h3 className="m-0 text-[22px] font-semibold">{s.title}</h3>
                <p className="m-0 leading-normal text-muted">{s.text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="mx-auto max-w-[1240px] px-5 pt-16 pb-16 sm:px-6">
          <div className="flex flex-wrap items-center gap-7 rounded-[26px] border border-coral bg-coral-tint p-6 sm:p-11">
            <h2 className="m-0 flex-[1_1_420px] font-display text-[clamp(26px,5vw,40px)] leading-[1.08] font-extrabold tracking-[-0.03em]">
              Попробуйте на своём деле
            </h2>
            <div className="flex flex-[1_1_300px] flex-col items-start gap-3">
              <Button asChild size="lg">
                <Link href="/login">
                  Начать разговор
                  <ArrowRight aria-hidden="true" />
                </Link>
              </Button>
              <Disclaimer />
            </div>
          </div>
        </section>
      </main>
      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-[1240px] flex-wrap gap-4 px-5 py-6 text-sm text-dim sm:px-6">
          <span>reqgraph · дипломный проект</span>
          <a href={REPO_URL} className="ml-auto text-dim">Исходный код на GitHub</a>
        </div>
      </footer>
    </>
  );
}
