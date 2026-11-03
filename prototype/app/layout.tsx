import type { Metadata } from "next";
import { Manrope, Space_Grotesk } from "next/font/google";
import "./globals.css";
import "./model-lab.css";

const manrope = Manrope({ variable: "--font-body", subsets: ["latin", "cyrillic"] });
const spaceGrotesk = Space_Grotesk({ variable: "--font-display", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Aftertime · Model Lab",
  description: "Безтериторіальна виконувана модель газу, електростанції, мережі, аварій і відновлення.",
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
  openGraph: {
    title: "Aftertime · Model Lab",
    description: "Газ → ТЕС → електромережа → споживач → аварія → відновлення.",
  },
  twitter: {
    card: "summary_large_image",
    title: "Aftertime · Model Lab",
    description: "Газ → ТЕС → електромережа → споживач → аварія → відновлення.",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="uk">
      <body className={`${manrope.variable} ${spaceGrotesk.variable}`}>{children}</body>
    </html>
  );
}
