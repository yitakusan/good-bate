// ============================================================
// FEATURE: AUTH
//
// [功能] 登录 / 客户注册表单
// [用途] 员工主界面、/apply、/me 共用
//
// [页面]
// frontend/src/AuthPanel.tsx
// frontend/src/App.tsx
// frontend/src/ApplyPage.tsx
// frontend/src/MePage.tsx
//
// [前端 API]
// frontend/src/api.ts → login() / registerCustomer()
//
// [后端接口]
// POST /api/auth/login
// POST /api/auth/register
//
// [后端] backend/app/auth.py
// [数据库] users, sessions
// [代码索引] docs/CODE_INDEX.md#feature-auth
// ============================================================
import { FormEvent, useState } from "react";

import {
  AuthUser,
  login,
  registerCustomer,
} from "./api";

function errorText(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

type Mode = "login" | "register";

export default function AuthPanel({
  title = "登录",
  allowRegister = false,
  onSuccess,
}: {
  title?: string;
  allowRegister?: boolean;
  onSuccess: (user: AuthUser) => void;
}) {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const user =
        mode === "register"
          ? await registerCustomer(email.trim(), password, displayName.trim())
          : await login(email.trim(), password);
      onSuccess(user);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel auth-panel">
      <h2>{mode === "register" ? "客户注册" : title}</h2>
      <form className="auth-form" onSubmit={(e) => void onSubmit(e)}>
        {mode === "register" ? (
          <label>
            昵称
            <input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              autoComplete="nickname"
            />
          </label>
        ) : null}
        <label>
          邮箱
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="username"
          />
        </label>
        <label>
          密码
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={mode === "register" ? 8 : 1}
            autoComplete={mode === "register" ? "new-password" : "current-password"}
          />
        </label>
        {error ? <p className="error">{error}</p> : null}
        <button type="submit" className="btn primary" disabled={busy}>
          {busy ? "提交中…" : mode === "register" ? "注册并登录" : "登录"}
        </button>
      </form>
      {allowRegister ? (
        <p className="muted auth-switch">
          {mode === "login" ? (
            <>
              没有账号？{" "}
              <button type="button" className="linkish" onClick={() => setMode("register")}>
                注册
              </button>
            </>
          ) : (
            <>
              已有账号？{" "}
              <button type="button" className="linkish" onClick={() => setMode("login")}>
                登录
              </button>
            </>
          )}
        </p>
      ) : null}
    </div>
  );
}
