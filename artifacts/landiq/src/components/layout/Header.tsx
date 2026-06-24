import { Menu, User, Settings, History as HistoryIcon, Plus } from "lucide-react";
import { Link } from "wouter";
import { Button } from "@/components/ui/button";

export function Header() {
  return (
    <header className="fixed top-0 left-0 right-0 z-40 lg:z-50 pointer-events-none">
      {/* Mobile Floating Header */}
      <div className="lg:hidden p-4 flex justify-between items-center pointer-events-auto">
        <div className="bg-white/90 dark:bg-[#1A1D24]/90 backdrop-blur-md px-4 py-2 rounded-full shadow-sm border border-border flex items-center gap-3">
          <div className="w-6 h-6 bg-primary rounded-sm flex items-center justify-center text-white font-bold text-xs">
            L
          </div>
          <span className="font-bold tracking-tight text-foreground">LandIQ</span>
        </div>
        <div className="bg-white/90 dark:bg-[#1A1D24]/90 backdrop-blur-md p-2 rounded-full shadow-sm border border-border flex items-center justify-center">
          <User className="w-5 h-5 text-foreground" />
        </div>
      </div>

      {/* Desktop Header */}
      <div className="hidden lg:flex h-16 bg-white dark:bg-[#1A1D24] border-b border-border items-center justify-between px-6 pointer-events-auto shadow-sm">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-primary rounded-md flex items-center justify-center text-white font-bold text-sm">
              L
            </div>
            <span className="font-bold text-xl tracking-tight text-foreground">LandIQ</span>
          </div>
          <div className="px-2 py-0.5 bg-muted rounded-md text-[10px] font-bold text-muted-foreground tracking-wider uppercase">
            LITE RUNTIME
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" className="rounded-full gap-2 border-border text-foreground hover:bg-muted" asChild>
             <Link href="/history">
                <HistoryIcon className="w-4 h-4" />
                History & Audit
             </Link>
          </Button>
          <Button variant="ghost" size="icon" className="rounded-full text-foreground hover:bg-muted">
            <Settings className="w-5 h-5" />
          </Button>
          <Button size="sm" className="rounded-full gap-2 bg-primary hover:bg-primary/90 text-white" asChild>
            <Link href="/analyse">
              <Plus className="w-4 h-4" />
              New Analysis
            </Link>
          </Button>
        </div>
      </div>
    </header>
  );
}
