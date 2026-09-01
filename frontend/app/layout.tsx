export const metadata = {
  title: "Enterprise Policy Copilot",
  description: "Permission-aware internal policy Q&A demo",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#0e1116", color: "#e6e6e6" }}>
        {children}
      </body>
    </html>
  );
}
