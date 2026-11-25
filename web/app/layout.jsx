import "./globals.css";
export const metadata = {
    title: "SM Terminal | Market Intelligence",
    description: "A keyboard-driven market terminal for global markets and NSE equities."
};
export default function RootLayout({ children }) {
    return (<html lang="en">
      <body>{children}</body>
    </html>);
}
