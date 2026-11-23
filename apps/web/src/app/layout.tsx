import type { Metadata, Viewport } from "next";

// Fonts are bundled from @fontsource, not fetched from Google at build time: the offline stand
// (T-507) builds without network. Cyrillic and Latin subsets load by unicode-range.
import "@fontsource-variable/onest";
import "@fontsource-variable/unbounded";
import "@fontsource/pt-serif/400.css";
import "@fontsource/pt-serif/700.css";

import { THEME_SCRIPT } from "@/components/ThemeToggle";
import { OwnKeyProvider } from "@/lib/own-key";

import "./globals.css";

export const metadata: Metadata = {
  title: "reqgraph",
  description: "Расскажите о своём деле — техническое задание мы напишем сами",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#1e2133" },
    { media: "(prefers-color-scheme: light)", color: "#f4f5f9" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <OwnKeyProvider>{children}</OwnKeyProvider>
      </body>
    </html>
  );
}
