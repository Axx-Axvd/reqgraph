import type { Metadata } from "next";

import { OwnKeyProvider } from "@/lib/own-key";

import "./globals.css";

export const metadata: Metadata = {
  title: "reqgraph",
  description:
    "Интервью с заказчиком -> требования -> модели как код -> проверки -> SRS и ТЗ",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru">
      <body>
        <OwnKeyProvider>{children}</OwnKeyProvider>
      </body>
    </html>
  );
}
