import Link from "next/link";

import { Disclaimer } from "@/components/Disclaimer";

export default function Home() {
  return (
    <main className="page narrow">
      <h1>reqgraph</h1>
      <p>
        Агенты ведут интервью с заказчиком, записывают требования, строят модели процессов и данных,
        проверяют их и собирают SRS и ТЗ по ГОСТ 34.602.
      </p>
      <p>
        <Link className="button" href="/projects">Мои проекты</Link>
      </p>
      <Disclaimer />
    </main>
  );
}
