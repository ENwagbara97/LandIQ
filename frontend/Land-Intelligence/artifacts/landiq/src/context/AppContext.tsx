import React, { createContext, useContext, useState, useRef, ReactNode } from "react";

export type Tab = 'map' | 'analyse' | 'gate' | 'report' | 'history';
export type AnalysisState = null | 'extracting' | 'gate' | 'complete';

interface FormData {
  area: string;
  persona: string;
  coordinates: string;
  coordMode: 'polygon' | 'point' | 'cogo' | 'text';
  cogoStartEasting: string;
  cogoStartNorthing: string;
  cogoStartCrs: string;
  cogoRows: Array<{ id: string, bearing: string, distance: string }>;
  file: File | null;
}

export type TileStyle = "satellite" | "esri_hybrid" | "osm";

interface AppContextType {
  activeTab: Tab;
  setActiveTab: (tab: Tab) => void;
  analysisState: AnalysisState;
  setAnalysisState: (state: AnalysisState) => void;
  formData: FormData;
  setFormData: React.Dispatch<React.SetStateAction<FormData>>;
  reportData: any;
  setReportData: React.Dispatch<React.SetStateAction<any>>;
  sessionId: string | null;
  setSessionId: React.Dispatch<React.SetStateAction<string | null>>;
  parcelCoords: any;
  setParcelCoords: React.Dispatch<React.SetStateAction<any>>;
  mapViewport: any;
  setMapViewport: React.Dispatch<React.SetStateAction<any>>;
  cogoDraftCoords: [number, number][];
  setCogoDraftCoords: React.Dispatch<React.SetStateAction<[number, number][]>>;
  cogoClosureGap: { errorMeters: number; isClosed: boolean } | null;
  setCogoClosureGap: React.Dispatch<React.SetStateAction<{ errorMeters: number; isClosed: boolean } | null>>;
  extractTriggerRef: React.MutableRefObject<(() => void) | null>;
  resetKey: number;
  incrementResetKey: () => void;
  selectedLotId: string | null;
  setSelectedLotId: React.Dispatch<React.SetStateAction<string | null>>;
  tileStyle: TileStyle;
  setTileStyle: React.Dispatch<React.SetStateAction<TileStyle>>;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const defaultFormData: FormData = {
  area: "",
  persona: "",
  coordinates: "",
  coordMode: 'text',
  cogoStartEasting: "",
  cogoStartNorthing: "",
  cogoStartCrs: "EPSG:32632",
  cogoRows: [{ id: "S1-S2", bearing: "", distance: "" }],
  file: null,
};

export function AppProvider({ children }: { children: ReactNode }) {
  const [activeTab, setActiveTab] = useState<Tab>('map');
  const [analysisState, setAnalysisState] = useState<AnalysisState>(null);
  const [formData, setFormData] = useState<FormData>(defaultFormData);
  const [reportData, setReportData] = useState<any>(null);
  
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [parcelCoords, setParcelCoords] = useState<any>(null);
  const [mapViewport, setMapViewport] = useState<any>(null);
  const [cogoDraftCoords, setCogoDraftCoords] = useState<[number, number][]>([]);
  const [cogoClosureGap, setCogoClosureGap] = useState<{ errorMeters: number; isClosed: boolean } | null>(null);
  const extractTriggerRef = useRef<(() => void) | null>(null);

  const [resetKey, setResetKey] = useState<number>(0);
  const incrementResetKey = () => setResetKey(prev => prev + 1);
  const [selectedLotId, setSelectedLotId] = useState<string | null>(null);
  const [tileStyle, setTileStyle] = useState<TileStyle>("satellite");

  return (
    <AppContext.Provider value={{ 
      activeTab, setActiveTab, 
      analysisState, setAnalysisState, 
      formData, setFormData, 
      reportData, setReportData,
      sessionId, setSessionId,
      parcelCoords, setParcelCoords,
      mapViewport, setMapViewport,
      cogoDraftCoords, setCogoDraftCoords,
      cogoClosureGap, setCogoClosureGap,
      extractTriggerRef,
      resetKey, incrementResetKey,
      selectedLotId, setSelectedLotId,
      tileStyle, setTileStyle,
    }}>
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
