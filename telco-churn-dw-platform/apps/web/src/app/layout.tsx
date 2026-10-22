import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { Providers } from "@/components/Providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "Telco Churn Analytics",
  description: "Customer churn warehouse: KPIs, OLAP explorer, churn predictions and offline data entry.",
  manifest: "/manifest.webmanifest",
  applicationName: "Telco Churn Analytics",
  appleWebApp: { capable: true, title: "Churn", statusBarStyle: "default" },
  icons: { icon: "/icons/favicon-32.png", apple: "/icons/apple-touch-icon.png" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#0d5c68" },
    { media: "(prefers-color-scheme: dark)", color: "#0a1316" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a href="#main" className="sr-only">Skip to content</a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
