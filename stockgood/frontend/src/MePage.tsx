import { useEffect, useState } from "react";

import AuthPanel from "./AuthPanel";
import {
  AuthUser,
  OrderRequestPublic,
  confirmDeposit,
  fetchMe,
  fetchMyOrderRequests,
} from "./api";

function errorText(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function formatYen(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  return `¥${value.toLocaleString("ja-JP")}`;
}

export default function MePage() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [requests, setRequests] = useState<OrderRequestPublic[]>([]);
  const [listError, setListError] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [busyCode, setBusyCode] = useState("");
  const [message, setMessage] = useState("");

  async function refreshUser() {
    try {
      const me = await fetchMe();
      setUser(me);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  async function loadRequests(filter = statusFilter) {
    setListError("");
    try {
      setRequests(await fetchMyOrderRequests(filter || undefined));
    } catch (err) {
      setListError(errorText(err));
    }
  }

  useEffect(() => {
    void refreshUser();
  }, []);

  useEffect(() => {
    if (user) void loadRequests();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  async function onConfirmDeposit(code: string) {
    setBusyCode(code);
    setListError("");
    setMessage("");
    try {
      await confirmDeposit(code);
      setMessage(`${code} 定金已确认，订单已正式提交`);
      await loadRequests();
    } catch (err) {
      setListError(errorText(err));
    } finally {
      setBusyCode("");
    }
  }

  if (loading) {
    return (
      <div className="app apply-app">
        <p className="muted">加载中…</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="app apply-app">
        <header className="top">
          <div className="brand">
            <h1>我的申请</h1>
            <p className="brand-flow">登录后查看绑定到账号的申请进度</p>
          </div>
          <p>
            <a href="/apply">去申请页</a>
          </p>
        </header>
        <AuthPanel
          title="客户登录"
          allowRegister
          onSuccess={(u) => {
            setUser(u);
          }}
        />
      </div>
    );
  }

  return (
    <div className="app apply-app">
      <header className="top">
        <div className="brand">
          <h1>我的申请</h1>
          <p className="brand-flow">
            {user.display_name || user.email} · {user.email}
          </p>
        </div>
        <div className="me-actions">
          <a href="/apply">申请下单</a>
        </div>
      </header>

      <div className="panel">
        <div className="row">
          <label>
            状态
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                void loadRequests(e.target.value);
              }}
            >
              <option value="">全部</option>
              <option value="pending_payment">待付定金</option>
              <option value="submitted">已提交</option>
              <option value="ordered">已下单</option>
              <option value="rejected">已拒绝</option>
            </select>
          </label>
          <button type="button" className="btn" onClick={() => void loadRequests()}>
            刷新
          </button>
        </div>
        {message ? <p className="ok-msg">{message}</p> : null}
        {listError ? <p className="error">{listError}</p> : null}
        {requests.length === 0 ? (
          <p className="muted">暂无绑定到本账号的申请。请先登录后在申请页提交。</p>
        ) : (
          <ul className="request-list">
            {requests.map((req) => (
              <li key={req.request_code} className="request-card">
                <div className="request-title">
                  <strong>{req.account_order_no || req.request_code}</strong> ·{" "}
                  {req.status_label}
                </div>
                <div>{req.name}</div>
                <div className="muted">
                  {req.shop || "—"} · ×{req.qty} · {formatYen(req.amount ?? req.unit_cost)}
                </div>
                {req.status === "pending_payment" ? (
                  <div className="me-deposit-row">
                    <span className="muted">
                      定金 {formatYen(req.deposit_amount)}（须确认付款后才会正式提交）
                    </span>
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={busyCode === req.request_code}
                      onClick={() => void onConfirmDeposit(req.request_code)}
                    >
                      {busyCode === req.request_code ? "确认中…" : "确认已付定金"}
                    </button>
                  </div>
                ) : null}
                {req.shop_order_ref ? (
                  <div className="muted">注文番号 {req.shop_order_ref}</div>
                ) : null}
                {req.reject_reason ? (
                  <div className="error">拒绝：{req.reject_reason}</div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
