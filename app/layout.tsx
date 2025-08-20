import './globals.css';

export const metadata = {
  title: 'ChatGPT',
  description: 'A modern ChatGPT interface with streaming support',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}