import { useState } from "react";
import { Menu, Settings, History as HistoryIcon, Plus, X, Sun, Moon, ChevronRight, Shield, FileText, HelpCircle, LogOut, User } from "lucide-react";
import { Link, useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import { useTheme } from "next-themes";

export function Header() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { theme, setTheme } = useTheme();
  const [, setLocation] = useLocation();

  return (
    <>
      <header className="fixed top-0 left-0 right-0 z-40 pointer-events-none">
        {/* Mobile Floating Header */}
        <div className="lg:hidden p-3 flex justify-between items-center pointer-events-auto">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setDrawerOpen(true)}
              className="w-9 h-9 bg-white/90 dark:bg-[#1A1D24]/90 backdrop-blur-md rounded-full shadow-sm border border-border flex items-center justify-center"
            >
              <Menu className="w-4 h-4 text-foreground" />
            </button>
            <div className="bg-white/90 dark:bg-[#1A1D24]/90 backdrop-blur-md px-3 py-1.5 rounded-full shadow-sm border border-border flex items-center gap-2">
              <div className="w-5 h-5 bg-primary rounded-sm flex items-center justify-center text-white font-bold text-[10px]">L</div>
              <span className="font-bold tracking-tight text-foreground text-sm">LandIQ</span>
            </div>
          </div>
          <button
            onClick={() => setDrawerOpen(true)}
            className="w-9 h-9 bg-white/90 dark:bg-[#1A1D24]/90 backdrop-blur-md rounded-full shadow-sm border border-border flex items-center justify-center"
          >
            <User className="w-4 h-4 text-foreground" />
          </button>
        </div>

        {/* Desktop Header */}
        <div className="hidden lg:flex h-14 bg-white dark:bg-[#1A1D24] border-b border-border items-center justify-between px-5 pointer-events-auto shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 bg-primary rounded-md flex items-center justify-center text-white font-bold text-xs">L</div>
            <span className="font-bold text-lg tracking-tight text-foreground">LandIQ</span>
          </div>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" className="rounded-full gap-1.5 text-muted-foreground hover:text-foreground text-xs h-8" asChild>
              <Link href="/history"><HistoryIcon className="w-3.5 h-3.5" />History</Link>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="rounded-full gap-1.5 text-muted-foreground hover:text-foreground text-xs h-8 px-3"
              onClick={() => setDrawerOpen(true)}
            >
              <Settings className="w-3.5 h-3.5" />Settings
            </Button>
            <Button size="sm" className="rounded-full gap-1.5 bg-primary hover:bg-primary/90 text-white h-8 text-xs px-3 ml-1" asChild>
              <Link href="/analyse"><Plus className="w-3.5 h-3.5" />New Analysis</Link>
            </Button>
          </div>
        </div>
      </header>

      {/* Drawer Overlay */}
      {drawerOpen && (
        <div className="fixed inset-0 z-[200] flex">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" onClick={() => setDrawerOpen(false)} />
          <div className="relative w-[280px] h-full bg-white dark:bg-[#1A1D24] shadow-2xl flex flex-col z-10 animate-in slide-in-from-left duration-300">
            {/* Drawer Header */}
            <div className="p-4 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 bg-primary rounded-md flex items-center justify-center text-white font-bold text-xs">L</div>
                <span className="font-bold tracking-tight text-foreground">LandIQ</span>
              </div>
              <button onClick={() => setDrawerOpen(false)} className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-muted text-muted-foreground">
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Profile */}
            <div className="p-4 border-b border-border cursor-pointer hover:bg-muted/50 transition-colors" onClick={() => { setLocation('/profile'); setDrawerOpen(false); }}>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-primary/10 rounded-full flex items-center justify-center">
                  <User className="w-5 h-5 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-sm text-foreground">Guest User</p>
                  <p className="text-xs text-muted-foreground">Free Plan · Upgrade</p>
                </div>
                <ChevronRight className="w-4 h-4 text-muted-foreground flex-shrink-0" />
              </div>
            </div>

            <div className="flex-1 overflow-y-auto">
              <div className="p-4">
                <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-3">Settings</p>
                <div className="space-y-1">
                  <div className="flex items-center justify-between py-2.5 px-3 rounded-xl hover:bg-muted/50 transition-colors">
                    <div className="flex items-center gap-3">
                      {theme === 'dark' ? <Moon className="w-4 h-4 text-muted-foreground" /> : <Sun className="w-4 h-4 text-muted-foreground" />}
                      <span className="text-sm text-foreground">{theme === 'dark' ? 'Dark Mode' : 'Light Mode'}</span>
                    </div>
                    <button
                      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                      className={`relative rounded-full transition-colors duration-200 ${theme === 'dark' ? 'bg-primary' : 'bg-muted-foreground/30'}`}
                      style={{ height: '22px', width: '40px' }}
                    >
                      <span className={`absolute top-0.5 left-0.5 w-[18px] h-[18px] rounded-full bg-white shadow-sm transition-transform duration-200 ${theme === 'dark' ? 'translate-x-[18px]' : 'translate-x-0'}`} />
                    </button>
                  </div>
                  <DrawerItem icon={<Shield className="w-4 h-4" />} label="Privacy Policy" onClick={() => setDrawerOpen(false)} />
                  <DrawerItem icon={<FileText className="w-4 h-4" />} label="Terms of Service" onClick={() => setDrawerOpen(false)} />
                  <DrawerItem icon={<HelpCircle className="w-4 h-4" />} label="Help & Support" onClick={() => setDrawerOpen(false)} />
                </div>
              </div>
              <div className="px-4">
                <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-3">Account</p>
                <div className="space-y-1">
                  <DrawerItem icon={<Settings className="w-4 h-4" />} label="Account Settings" onClick={() => { setLocation('/profile'); setDrawerOpen(false); }} />
                  <DrawerItem icon={<HistoryIcon className="w-4 h-4" />} label="Analysis History" onClick={() => { setLocation('/history'); setDrawerOpen(false); }} />
                </div>
              </div>
            </div>

            <div className="p-4 border-t border-border">
              <button className="w-full flex items-center gap-3 py-2.5 px-3 rounded-xl hover:bg-red-50 dark:hover:bg-red-950/30 text-red-500 transition-colors text-sm font-medium">
                <LogOut className="w-4 h-4" />Sign Out
              </button>
              <p className="text-[10px] text-muted-foreground text-center mt-3">© 2026 LandIQ. All rights reserved.</p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function DrawerItem({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-full flex items-center justify-between py-2.5 px-3 rounded-xl hover:bg-muted/50 transition-colors group">
      <div className="flex items-center gap-3">
        <span className="text-muted-foreground">{icon}</span>
        <span className="text-sm text-foreground">{label}</span>
      </div>
      <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/50 group-hover:text-muted-foreground transition-colors" />
    </button>
  );
}
