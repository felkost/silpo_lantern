/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Plan section 7.1: "Frontend | React / Vite / TS". The recovery card
// (Diagnosis+disclosure / Consent / Receipt) landed.
//
// the interface gate is Vitest component tests + a pytest
// API-negative suite, not Playwright -- the plan's own pass criterion
// ("a write is impossible before exact consent") is an API property a
// request tests more directly than a browser driver does.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
  },
});
