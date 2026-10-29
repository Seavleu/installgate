import type { Metadata } from "next";
import { IBM_Plex_Sans, JetBrains_Mono } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";

const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-sans",
});
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "600", "700"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "InstallGate",
  description: "Pre-install trust gate for coding agents",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body className="min-h-[100dvh]">{children}</body>
    </html>
  );
}
