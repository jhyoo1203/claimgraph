import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "ClaimGraph",
  description: "출처와 주장 사이의 연결을 투명하게 보여주는 AI 리서치 워크스페이스",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
