from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.auth import create_user
from app.main import app
from harness import IsolatedDbTestCase


class RolePermissionTests(IsolatedDbTestCase):
    auth_required = True

    def setUp(self) -> None:
        super().setUp()
        create_user(
            email="cust@example.com",
            password="password1",
            role="customer",
            display_name="Cust",
        )
        create_user(
            email="wh@example.com",
            password="password1",
            role="warehouse",
            display_name="Wh",
        )
        create_user(
            email="fin@example.com",
            password="password1",
            role="finance",
            display_name="Fin",
        )
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        self.addCleanup(self._cm.__exit__, None, None, None)

    def _login(self, email: str) -> TestClient:
        res = self.client.post(
            "/api/auth/login",
            json={"email": email, "password": "password1"},
        )
        self.assertEqual(res.status_code, 200, res.text)
        return self.client

    def test_customer_cannot_list_staff_orders(self) -> None:
        self._login("cust@example.com")
        res = self.client.get("/api/orders")
        self.assertEqual(res.status_code, 403)

    def test_warehouse_cannot_export_fee_detail(self) -> None:
        self._login("wh@example.com")
        res = self.client.get("/api/outbound-batches/1/fee-detail.xlsx")
        self.assertEqual(res.status_code, 403)

    def test_warehouse_cannot_patch_finance(self) -> None:
        self._login("wh@example.com")
        res = self.client.patch(
            "/api/outbound-batches/1/finance",
            json={"amount_received_cny": 1},
        )
        self.assertEqual(res.status_code, 403)

    def test_finance_can_reach_fee_detail_endpoint(self) -> None:
        self._login("fin@example.com")
        res = self.client.get("/api/outbound-batches/1/fee-detail.xlsx")
        self.assertIn(res.status_code, (200, 404))
        self.assertNotEqual(res.status_code, 403)


class DualAuthPathTests(IsolatedDbTestCase):
    auth_required = True
    admin_token = "legacy-test-token"

    def setUp(self) -> None:
        super().setUp()
        create_user(
            email="cust@example.com",
            password="password1",
            role="customer",
            display_name="Cust",
        )
        create_user(
            email="wh@example.com",
            password="password1",
            role="warehouse",
            display_name="Wh",
        )
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        self.addCleanup(self._cm.__exit__, None, None, None)

    def _login(self, email: str) -> None:
        res = self.client.post(
            "/api/auth/login",
            json={"email": email, "password": "password1"},
        )
        self.assertEqual(res.status_code, 200, res.text)

    def test_missing_cookie_and_token_is_401(self) -> None:
        res = self.client.get("/api/orders")
        self.assertEqual(res.status_code, 401)

    def test_wrong_admin_token_is_401(self) -> None:
        res = self.client.get(
            "/api/orders", headers={"X-Admin-Token": "not-the-token"}
        )
        self.assertEqual(res.status_code, 401)

    def test_legacy_token_without_cookie_is_admin(self) -> None:
        headers = {"X-Admin-Token": self.admin_token}
        res = self.client.get("/api/orders", headers=headers)
        self.assertEqual(res.status_code, 200, res.text)
        fee = self.client.get(
            "/api/outbound-batches/1/fee-detail.xlsx", headers=headers
        )
        self.assertIn(fee.status_code, (200, 404))
        self.assertNotEqual(fee.status_code, 403)

    def test_customer_session_is_not_escalated_by_admin_token(self) -> None:
        self._login("cust@example.com")
        res = self.client.get(
            "/api/orders",
            headers={"X-Admin-Token": self.admin_token},
        )
        self.assertEqual(res.status_code, 403)

    def test_warehouse_session_still_cannot_export_fee_detail_with_token(self) -> None:
        self._login("wh@example.com")
        res = self.client.get(
            "/api/outbound-batches/1/fee-detail.xlsx",
            headers={"X-Admin-Token": self.admin_token},
        )
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
