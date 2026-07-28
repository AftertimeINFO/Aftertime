import type { Metadata } from "next";
import { Manrope, Space_Grotesk } from "next/font/google";
import "./globals.css";

const manrope = Manrope({ variable: "--font-body", subsets: ["latin", "cyrillic"] });
const spaceGrotesk = Space_Grotesk({ variable: "--font-display", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "ORB · Social Resource Planing",
  description: "Прототип системы физического учёта материи и её трансформаций.",
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
  openGraph: {
    title: "ORB · Social Resource Planing",
    description: "Планетарный учёт материи и её трансформаций.",
    images: [{ url: "/og.png", width: 1746, height: 907, alt: "ORB — планетарный учёт материи" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "ORB · Social Resource Planing",
    description: "Планетарный учёт материи и её трансформаций.",
    images: ["/og.png"],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body className={`${manrope.variable} ${spaceGrotesk.variable}`}>{children}</body>
    </html>
  );
}
