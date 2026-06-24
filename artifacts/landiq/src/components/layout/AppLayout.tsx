import { ReactNode } from "react";
import { BottomNav } from "./BottomNav";
import { Header } from "./Header";

export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-[100dvh] bg-background flex flex-col lg:flex-row overflow-hidden">
      <Header />
      
      <main className="flex-1 flex flex-col relative w-full lg:pt-16 h-[100dvh] lg:h-screen">
        {children}
      </main>

      <BottomNav />
    </div>
  );
}
