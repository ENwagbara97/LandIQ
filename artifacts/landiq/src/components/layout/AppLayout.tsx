import { ReactNode } from "react";
import { BottomNav } from "./BottomNav";
import { Header } from "./Header";

export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="bg-background overflow-hidden" style={{ height: '100dvh' }}>
      <Header />

      {/* Desktop: push content below fixed header */}
      <main className="hidden lg:flex lg:pt-14 h-full w-full flex-row overflow-hidden">
        {children}
      </main>

      {/* Mobile: full-bleed, header floats on top, bottom nav at bottom */}
      <main className="lg:hidden relative w-full overflow-hidden" style={{ height: '100dvh' }}>
        {children}
        <BottomNav />
      </main>
    </div>
  );
}
