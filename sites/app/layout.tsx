import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "周边履约工作台",
  description: "管理日本采购、1210 保税仓与国内履约。",
  icons: { icon: "/brand.svg" },
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
