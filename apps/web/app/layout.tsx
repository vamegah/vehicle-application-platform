import type { ReactNode } from "react";

export const metadata = {
  title: "AutoReliance AI",
  description: "Automotive engineering, quality, and release assurance",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
