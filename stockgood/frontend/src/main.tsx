// ============================================================
// SHARED MODULE
//
// [用途] 前端路由分流：/apply 申请页、/me 客户门户、其余员工主界面
// [使用功能]
// FEATURE: ORDER_REQUEST
// FEATURE: CUSTOMER_PORTAL
// FEATURE: AUTH（员工主界面未登录时走 App.tsx 内 AuthPanel）
// [代码索引] docs/CODE_INDEX.md#shared-modules
// ============================================================
import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import ApplyPage from "./ApplyPage";
import MePage from "./MePage";
import "./styles.css";

const path = window.location.pathname.replace(/\/+$/, "") || "/";
const isApply = path === "/apply" || path.startsWith("/apply/");
const isMe = path === "/me" || path.startsWith("/me/");

function Page() {
  if (isApply) return <ApplyPage />;
  if (isMe) return <MePage />;
  return <App />;
}

function mount() {
  ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
    <React.StrictMode>
      <Page />
    </React.StrictMode>,
  );
}

/** Keep a single main UI tab: extra tabs ping and close if another already answered. */
function claimMainUiThenMount() {
  if (isApply || isMe || typeof BroadcastChannel === "undefined") {
    mount();
    return;
  }
  const ch = new BroadcastChannel("stockgood-ui");
  let primary = false;
  const timer = window.setTimeout(() => {
    primary = true;
    ch.onmessage = (ev) => {
      if (ev.data === "ping") ch.postMessage("pong");
    };
    mount();
  }, 80);
  ch.onmessage = (ev) => {
    if (ev.data === "pong" && !primary) {
      window.clearTimeout(timer);
      try {
        window.close();
      } catch {
        /* browsers may ignore close on user-opened tabs */
      }
    }
  };
  ch.postMessage("ping");
}

claimMainUiThenMount();
