import type { Metadata } from "next";
// Fonts are bundled from npm (not fetched from Google) so the demo runs offline.
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
import "./globals.css";
import { en } from "@/lib/i18n/en";

export const metadata: Metadata = {
  title: en["app.name"],
  description: en["app.tagline"],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
