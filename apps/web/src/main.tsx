import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.tsx";
// The only stylesheet, imported here and never from App.tsx (see console.css).
import "./console.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
