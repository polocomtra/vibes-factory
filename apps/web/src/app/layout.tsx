import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "VibesFactory",
  description: "Build. Orchestrate. Deploy.",
  icons: {
    icon: "/assets/images/VibesFactory-favicon.png",
    shortcut: "/assets/images/VibesFactory-favicon.png",
    apple: "/assets/images/VibesFactory-favicon.png",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-theme="dark">
      <body>{children}</body>
    </html>
  );
}
