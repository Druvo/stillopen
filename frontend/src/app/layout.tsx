import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { Providers } from "@/components/providers";

export const metadata: Metadata = { title: "StillOpen", description: "Your job search, in one place." };

// Design system (design.md): Bento Grid in light mode, Dark Command Center in dark mode, one shared humanist
// sans (Albert Sans) throughout. Vendored locally via next/font/local (same file as the public pages'
// static/vendor/fonts/ -- see that folder's NOTICE.md -- nothing is fetched from Google at runtime or build
// time beyond the one-time vendoring; next/font/local never makes a network request itself).
const albertSans = localFont({
  src: "../../public/fonts/albert-sans-variable.woff2",
  variable: "--font-albert-sans",
  weight: "100 900",
  display: "swap",
});

// Applies the remembered colour mode before first paint so there is no flash. `data-default-theme` on <html>
// below is this build's fallback ("dark" by default); the Django server that serves this shell patches that
// attribute per its own Site configuration > Appearance setting (tracker/views_app.py), so an admin's choice
// takes effect without a rebuild. A visitor's own choice, once made (the "so-theme" key, shared with the
// public pages), always wins over either default.
const themeScript = `try{var s=localStorage.getItem("so-theme");var t=(s==="dark"||s==="light")?s:(document.documentElement.getAttribute("data-default-theme")||"dark");if(t==="light")document.documentElement.dataset.theme="light"}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-default-theme="dark" data-theme="dark" className={albertSans.variable} suppressHydrationWarning>
      <head>
        <script>{themeScript}</script>
      </head>
      <body className="min-h-screen font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
