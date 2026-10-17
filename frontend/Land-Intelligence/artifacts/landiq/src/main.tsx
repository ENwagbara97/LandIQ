import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(<App />);

// Dismiss splash screen once React has started rendering
if (typeof (window as any).__hideSplash === "function") {
  (window as any).__hideSplash();
}
