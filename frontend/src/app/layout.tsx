import type { Metadata } from "next";
import { DotGothic16, Silkscreen } from "next/font/google";
import { ThemeProvider } from "@/components/theme";
import "./globals.css";

// Body text: a pixel face drawn on a 16px grid, so it's crisp (and readable) at exactly
// 16px. Pixelify Sans drew 5 and S almost identically; Tiny5 was too coarse to read.
const dotGothic = DotGothic16({
  variable: "--font-pixel",
  weight: "400",
  subsets: ["latin"],
});

// Menu labels and names, set in caps like the handheld menus.
const silkscreen = Silkscreen({
  variable: "--font-silkscreen",
  weight: ["400", "700"],
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "RAGNaw",
  description: "Ask anything about Pokémon, answered from PokeAPI data.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // next-themes sets data-frame on <html> before hydration.
    <html
      lang="en"
      className={`${dotGothic.variable} ${silkscreen.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
