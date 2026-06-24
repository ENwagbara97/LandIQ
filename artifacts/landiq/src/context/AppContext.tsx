import React, { createContext, useContext, useState, ReactNode } from "react";

export type Tab = 'map' | 'analyse' | 'gate' | 'report' | 'history';
export type AnalysisState = null | 'extracting' | 'gate' | 'complete';

interface FormData {
  area: string;
  persona: string;
  coordinates: string;
  file: File | null;
}

interface AppContextType {
  activeTab: Tab;
  setActiveTab: (tab: Tab) => void;
  analysisState: AnalysisState;
  setAnalysisState: (state: AnalysisState) => void;
  formData: FormData;
  setFormData: React.Dispatch<React.SetStateAction<FormData>>;
  reportData: any;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export function AppProvider({ children }: { children: ReactNode }) {
  const [activeTab, setActiveTab] = useState<Tab>('map');
  const [analysisState, setAnalysisState] = useState<AnalysisState>(null);
  const [formData, setFormData] = useState<FormData>({
    area: "",
    persona: "Everyday Land Buyer",
    coordinates: "",
    file: null,
  });

  const reportData = {
    score: 82,
    verdict: "GREEN — PROCEED",
    summary: "This parcel is located in a stable cadastral zone with minimal risk factors. The computed area closely matches the registry records. No significant encumbrances were detected.",
    metrics: {
      elevation: "142m MSL",
      slope: "4.2° Avg",
      floodRisk: "Low (0.1%)",
      vegDensity: "64% NDVI"
    }
  };

  return (
    <AppContext.Provider value={{ activeTab, setActiveTab, analysisState, setAnalysisState, formData, setFormData, reportData }}>
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext() {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error("useAppContext must be used within an AppProvider");
  }
  return context;
}
