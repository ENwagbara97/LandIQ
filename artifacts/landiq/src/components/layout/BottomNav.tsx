import { useEffect, useState } from "react";
import { Link, useLocation } from "wouter";
import { Map, FileText, Activity, History } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAppContext, Tab } from "@/context/AppContext";

export function BottomNav() {
  const [location] = useLocation();
  const { activeTab, setActiveTab } = useAppContext();

  const tabs: { id: Tab; label: string; icon: React.ElementType; href: string }[] = [
    { id: 'map', label: 'Map', icon: Map, href: '/' },
    { id: 'analyse', label: 'Analyse', icon: Activity, href: '/analyse' },
    { id: 'report', label: 'Report', icon: FileText, href: '/report' },
    { id: 'history', label: 'History', icon: History, href: '/history' }
  ];

  useEffect(() => {
    const currentTab = tabs.find(t => t.href === location || (location === '/' && t.id === 'map'))?.id || 'map';
    setActiveTab(currentTab);
  }, [location, setActiveTab]);

  return (
    <div className="fixed bottom-0 left-0 right-0 h-[80px] bg-white dark:bg-[#1A1D24] border-t border-border z-50 flex items-center justify-around px-2 lg:hidden shadow-[0_-4px_24px_rgba(0,0,0,0.04)] dark:shadow-none">
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        const Icon = tab.icon;
        
        return (
          <Link 
            key={tab.id} 
            href={tab.href}
            className="relative flex flex-col items-center justify-center w-16 h-14"
            data-testid={`nav-${tab.id}`}
          >
            <div className={cn(
              "absolute inset-0 rounded-full transition-all duration-300 ease-out z-0",
              isActive ? "bg-primary/10 dark:bg-primary/20 scale-100 opacity-100" : "scale-50 opacity-0"
            )} />
            <Icon 
              className={cn(
                "w-6 h-6 mb-1 z-10 transition-colors duration-200",
                isActive ? "text-primary dark:text-primary" : "text-muted-foreground"
              )} 
            />
            <span className={cn(
              "text-[10px] font-medium z-10 transition-colors duration-200",
              isActive ? "text-primary dark:text-primary" : "text-muted-foreground"
            )}>
              {tab.label}
            </span>
          </Link>
        );
      })}
    </div>
  );
}
