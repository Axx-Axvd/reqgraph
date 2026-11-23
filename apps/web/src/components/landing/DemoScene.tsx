// The demo of the landing page (T-509, board «Главная»): a question, the client's answer, the key phrase
// marked, a draft requirement, a new node on the graph and a topic closed. CSS only; with «reduce motion»
// the animation is off and the final picture shows. Content: examples/garage61 (BR-001 from TURN-0004).
const STEP = "Есть ли ещё проблема, которую должна решить система?";

export function DemoScene() {
  return (
    <figure
      className="demo m-0 min-w-0 flex-[1_1_480px] overflow-hidden rounded-[22px] border border-line bg-surface shadow-(--shadow)"
      aria-label="Пример: ответ заказчика превращается в черновик требования"
    >
      <div className="flex min-h-11 items-center gap-2.5 border-b border-line px-4 text-[13px] text-muted">
        <span className="size-2 rounded-full bg-mint" aria-hidden="true" />
        Интервью · автосервис «Гараж 61»
      </div>
      <div className="grid gap-4 p-5 sm:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-2.5">
          <p className="demo-q m-0 max-w-[92%] rounded-[20px_20px_20px_6px] bg-raised px-4 py-3 text-[15px] leading-normal">{STEP}</p>
          <p className="demo-a m-0 max-w-[92%] self-end rounded-[20px_20px_6px_20px] bg-coral-tint px-4 py-3 text-[15px] leading-normal text-client shadow-[inset_0_0_0_1px_var(--coral-line)]">
            Неявки. <mark className="demo-hl bg-transparent text-inherit">Примерно 15% слотов пропадают</mark>: клиент записался и не
            приехал. Хотим снизить хотя бы вдвое.
          </p>
          <div className="demo-card flex flex-col gap-1.5 rounded-2xl border border-line-2 bg-raised px-3.5 py-3">
            <span className="inline-flex items-center gap-2 text-xs text-muted">
              <span className="size-2 rounded-full bg-coral-text" aria-hidden="true" />
              Черновик требования · цель
            </span>
            <span className="text-sm leading-snug">Неявок станет вдвое меньше: с 15% до 7% записей за полгода.</span>
          </div>
        </div>
        <div className="flex min-w-0 flex-col gap-3" aria-hidden="true">
          <div className="relative">
            <svg viewBox="0 0 220 180" className="w-full">
              <path d="M38 40 C 60 56, 78 66, 92 76" fill="none" stroke="var(--line-2)" strokeWidth="1.4" />
              <path d="M184 40 C 160 56, 142 66, 130 76" fill="none" stroke="var(--line-2)" strokeWidth="1.4" />
              <path className="demo-edge" pathLength={1} d="M50 152 C 70 136, 88 124, 98 110" fill="none" stroke="var(--mint)" strokeWidth="1.8" strokeLinecap="round" />
              <circle cx="30" cy="34" r="9" fill="var(--surface)" stroke="var(--line-2)" strokeWidth="1.4" />
              <circle cx="190" cy="34" r="8" fill="var(--surface)" stroke="var(--line-2)" strokeWidth="1.4" />
              <rect x="58" y="76" width="104" height="34" rx="10" fill="var(--raised)" stroke="var(--line-2)" strokeWidth="1.4" />
              <circle className="demo-node" cx="44" cy="158" r="11" fill="var(--mint-fill)" stroke="var(--mint)" strokeWidth="2" />
            </svg>
            <span className="absolute top-[52%] left-1/2 -translate-x-1/2 -translate-y-1/2 text-[11px] whitespace-nowrap">Запись на ремонт</span>
            <span className="absolute top-[10%] left-[20%] -translate-y-1/2 text-[11px] text-muted">Клиент</span>
            <span className="absolute top-[10%] right-[20%] -translate-y-1/2 text-[11px] text-muted">Мастер</span>
            <span className="demo-label absolute top-[88%] left-[28%] -translate-y-1/2 text-[11px] whitespace-nowrap text-mint-text">меньше неявок</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="demo-tile flex flex-col gap-1 rounded-xl border px-2.5 py-2">
              <span className="text-xs">Цели</span>
              <span className="text-xs tabular-nums">1/1</span>
            </div>
            <div className="flex flex-col gap-1 rounded-xl border border-line bg-raised px-2.5 py-2">
              <span className="text-xs">Правила</span>
              <span className="text-xs text-muted tabular-nums">0/3</span>
            </div>
          </div>
        </div>
      </div>
      <figcaption className="border-t border-line px-4 py-3 text-[13px] text-dim">
        Ответ заказчика превращается в черновик требования, узел графа и закрытую тему
      </figcaption>
    </figure>
  );
}
