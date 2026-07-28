import type { Metadata } from "next";
import { Manrope, Space_Grotesk } from "next/font/google";
import "./globals.css";

const manrope = Manrope({ variable: "--font-body", subsets: ["latin", "cyrillic"] });
const spaceGrotesk = Space_Grotesk({ variable: "--font-display", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "ORB · Nitrogen World Model",
  description: "Модель материи, инфраструктуры и организаций для прогнозирования будущих состояний.",
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
  openGraph: {
    title: "ORB · Nitrogen World Model",
    description: "От азота и энергии до производства, логистики и урожая.",
    images: [{ url: "/og-v2.png", width: 1746, height: 907, alt: "ORB — модель материи, производства и инфраструктуры" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "ORB · Nitrogen World Model",
    description: "От азота и энергии до производства, логистики и урожая.",
    images: ["/og-v2.png"],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body className={`${manrope.variable} ${spaceGrotesk.variable}`}>{children}</body>
    </html>
  );
}
