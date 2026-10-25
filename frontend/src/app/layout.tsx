import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import "./globals.css";
import { Providers } from "@/components/providers";

export const metadata: Metadata = { title: "StillOpen", description: "Your job search, in one place." };

// Applies the remembered display choices before first paint so there is no flash: colour mode (same key and rule as the classic pages and the
// sign-in screens, light unless the person chose dark), text size and density. The server's copy (preferences) takes over once /me has answered.
const themeScript = `try{var d=document.documentElement,s=localStorage;if(s.getItem("so-theme")==="dark")d.dataset.theme="dark";var t=s.getItem("so-text");if(t==="large"||t==="larger")d.dataset.text=t;if(s.getItem("so-density")==="compact")d.dataset.density="compact"}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={GeistSans.variable} suppressHydrationWarning>
      <head>
        <script>{themeScript}</script>
      </head>
      <body className="min-h-screen font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
