import type { Metadata } from "next";

import { QueryProvider } from "@/components/providers/QueryProvider";
import { ThemeProvider } from "@/components/providers/ThemeProvider";

import "./globals.css";

export const metadata: Metadata = {
  title: "Vigil — Observability & Incident Intelligence",
  description:
    "Real-time observability platform with anomaly detection and AI incident analysis",
};

/**
 * Blocking inline script — runs synchronously in <head> before any paint.
 * Reads localStorage and applies the correct class to <html> immediately,
 * preventing any flash of the wrong theme.
 * Default when no stored preference exists: dark.
 */
const themeScript = `(function(){try{var s=localStorage.getItem('vigil-color-scheme');if(s==='dark'){document.documentElement.classList.add('dark')}else{document.documentElement.classList.remove('dark')}}catch(e){document.documentElement.classList.remove('dark')}})();`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Must be the very first child of <head> to block paint */}
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-screen antialiased">
        <ThemeProvider>
          <QueryProvider>{children}</QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
