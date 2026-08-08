import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import ApplyPage from "./ApplyPage";
import "./styles.css";

const path = window.location.pathname.replace(/\/+$/, "") || "/";
const isApply = path === "/apply" || path.startsWith("/apply/");

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>{isApply ? <ApplyPage /> : <App />}</React.StrictMode>,
);
