import { useEffect } from "react";
import { Link, useLocation } from "wouter";
import { Map, FileText, History, ScanLine } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAppContext, Tab } from "@/context/AppContext";

export function BottomNav() {
  const [location] = useLocation();
  const { activeTab, setActiveTab } = useAppContext();

  const tabs: { id: Tab; label: string; icon: React.ElementType; href: string }[] = [
    { id: 'map', label: 'Map', icon: Map, href: '/' },
    { id: 'analyse', label: 'Analyse', icon: ScanLine, href: '/analyse' },
    { id: 'report', label: 'Report', icon: FileText, href: '/report' },
    { id: 'history', label: 'History', icon: History, href: '/history' },
  ];

  useEffect(() => {
    const currentTab = tabs.find(t =>
      t.href === location || (location === '/' && t.id === 'map')
    )?.id || 'map';
    setActiveTab(currentTab);
  }, [location]);

  return (
    <div className="fixed bottom-0 left-0 right-0 h-[72px] bg-white/95 dark:bg-[#1A1D24]/95 backdrop-blur-md border-t border-border z-[100] flex items-center justify-around px-2 lg:hidden shadow-[0_-1px_0_rgba(0,0,0,0.06)]">
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        const Icon = tab.icon;
        return (
          <Link
            key={tab.id}
            href={tab.href}
            className="relative flex flex-col items-center justify-center flex-1 h-full gap-1 select-none"
            data-testid={`nav-${tab.id}`}
          >
            <div className={cn(
              "w-12 h-7 rounded-full flex items-center justify-center transition-all duration-200",
              isActive ? "bg-primary/12 dark:bg-primary/20" : "bg-transparent"
            )}>
              <Icon className={cn(
                "w-5 h-5 transition-colors duration-200",
                isActive ? "text-primary" : "text-muted-foreground"
              )} />
            </div>
            <span className={cn(
              "text-[10px] font-medium leading-none transition-colors duration-200",
              isActive ? "text-primary font-semibold" : "text-muted-foreground"
            )}>
              {tab.label}
            </span>
          </Link>
        );
      })}
    </div>
  );
}
