import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "../engine/App";
import "../engine/styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("Missing application root");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
