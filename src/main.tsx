import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import "./styles/app.css";
import "./styles/extra.css";

const container = document.getElementById("root");
if (!container) throw new Error("No se encontró el contenedor #root");

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
