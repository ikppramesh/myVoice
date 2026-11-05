import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "myVoice — speak any text in your own cloned voice",
  description:
    "Clone your voice locally and turn any text or podcast script into natural speech in English and Indian languages. Free, private, no upload.",
  openGraph: {
    title: "myVoice — speak any text in your own cloned voice",
    description: "Private, local voice cloning with English and Indian-language speech.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
