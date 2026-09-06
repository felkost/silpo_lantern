import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Plan section 7.1: "Frontend | React / Vite / TS". Scaffold only this
// stage — the recovery card (Diagnosis+disclosure / Consent / Receipt)
// lands at G5+G6, once there is a backend session/SSE API to render.
export default defineConfig({
  plugins: [react()],
});
