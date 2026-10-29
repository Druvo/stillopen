import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { Providers } from "@/components/providers";

export const metadata: Metadata = { title: "StillOpen", description: "Your job search, in one place." };

// Typography DNA studied from impeccable.style (2026-10-29): a tall, ultralight condensed display face paired
// with a plain humanist body face. Both are vendored locally via next/font/local (same files as the public
// pages' static/vendor/fonts/ -- see that folder's NOTICE.md -- nothing is fetched from Google at runtime or
// build time beyond the one-time vendoring; next/font/local never makes a network request itself).
const albertSans = localFont({
  src: "../../public/fonts/albert-sans-variable.woff2",
  variable: "--font-albert-sans",
  weight: "100 900",
  display: "swap",
});
const alumniSans = localFont({
  src: "../../public/fonts/alumni-sans-variable.woff2",
  variable: "--font-alumni-sans",
  weight: "100 900",
  display: "swap",
});

// Applies the remembered colour mode before first paint so there is no flash. Same key and same rule as the classic pages and the sign-in
// screens (light unless the person chose dark), so the choice follows them everywhere.
const themeScript = `try{if(localStorage.getItem("so-theme")==="dark")document.documentElement.dataset.theme="dark"}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${albertSans.variable} ${alumniSans.variable}`} suppressHydrationWarning>
      <head>
        <script>{themeScript}</script>
      </head>
      <body className="min-h-screen font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
