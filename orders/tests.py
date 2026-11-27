import os
import secrets
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import identify_hasher
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import Client, TestCase
from django.urls import reverse

from .access import APPROVER, CREATOR
from .models import PurchaseOrder


class AccountAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.accounts = {
            "creator1": {CREATOR}, "creator2": {CREATOR},
            "approver1": {APPROVER}, "lead1": {CREATOR, APPROVER},
        }
        cls.passwords = {user: secrets.token_urlsafe(24) for user in cls.accounts}
        with patch.dict(os.environ, {f"{u.upper()}_PASSWORD": p for u, p in cls.passwords.items()}):
            call_command("provision_accounts")
        cls.users = {user.username: user for user in get_user_model().objects.all()}
        cls.private = PurchaseOrder.objects.create(number="PO-PRIVATE", creator=cls.users["creator1"])
        cls.submitted = PurchaseOrder.objects.create(
            number="PO-SUBMITTED", creator=cls.users["creator2"], status=PurchaseOrder.Status.SUBMITTED
        )
        cls.lead_draft = PurchaseOrder.objects.create(number="PO-LEAD", creator=cls.users["lead1"])

    def test_accounts_can_sign_in_with_argon2_and_keep_passwords_on_startup(self):
        call_command("provision_accounts")
        for username, expected in self.accounts.items():
            with self.subTest(username=username):
                user = get_user_model().objects.get(username=username)
                self.assertEqual(set(user.groups.values_list("name", flat=True)), expected)
                self.assertEqual(identify_hasher(user.password).algorithm, "argon2")
                self.assertTrue(user.password.startswith("argon2$argon2id$"))
                self.assertEqual(user.password, self.users[username].password)
                result = self.client.post(reverse("login"), {
                    "username": username, "password": self.passwords[username],
                })
                self.assertRedirects(result, reverse("workspace"))
                self.assertContains(self.client.get("/"), username)
                self.client.post(reverse("logout"))
                self.assertEqual(self.client.get(reverse("order-list")).status_code, 401)

    def test_missing_provisioning_secret_rolls_back_new_accounts(self):
        get_user_model().objects.filter(username="approver1").delete()
        with patch.dict(os.environ, {"APPROVER1_PASSWORD": ""}), self.assertRaises(CommandError):
            call_command("provision_accounts")
        self.assertFalse(get_user_model().objects.filter(username="approver1").exists())

    def test_anonymous_api_is_401_even_without_csrf_and_health_remains_public(self):
        browser = Client(enforce_csrf_checks=True)
        for path in [reverse("order-list"), reverse("order-detail", args=[self.private.pk]), reverse("approval-queue")]:
            self.assertEqual(browser.get(path).status_code, 401)
        self.assertEqual(browser.post(reverse("order-list"), {}).status_code, 401)
        self.assertEqual(browser.get("/health").status_code, 200)
        browser.force_login(self.users["creator1"])
        self.assertEqual(browser.post(reverse("order-list"), {"number": "UNSAFE"}).status_code, 403)
        self.assertFalse(PurchaseOrder.objects.filter(number="UNSAFE").exists())

    def test_creators_are_limited_to_their_own_orders_and_cannot_access_finance(self):
        self.client.force_login(self.users["creator2"])
        self.assertEqual([row["id"] for row in self.client.get("/api/pos/").json()["orders"]], [self.submitted.pk])
        hidden = self.client.get(reverse("order-detail", args=[self.private.pk]))
        missing = self.client.get(reverse("order-detail", args=[999999]))
        self.assertEqual((hidden.status_code, missing.status_code), (404, 404))
        self.assertEqual(hidden.json(), missing.json())
        self.assertEqual(self.client.get(reverse("approval-queue")).status_code, 403)
        self.client.force_login(self.users["creator1"])
        self.assertEqual(self.client.get(reverse("order-detail", args=[self.private.pk])).status_code, 200)

    def test_approver_and_dual_role_scopes(self):
        for username, expected in [
            ("approver1", [self.submitted.pk]), ("lead1", [self.lead_draft.pk, self.submitted.pk])
        ]:
            self.client.force_login(self.users[username])
            self.assertEqual([r["id"] for r in self.client.get("/api/pos/").json()["orders"]], expected)
            queue = self.client.get(reverse("approval-queue")).json()["orders"]
            self.assertEqual([r["id"] for r in queue], [self.submitted.pk])
            self.assertEqual(self.client.get(reverse("order-detail", args=[self.private.pk])).status_code, 404)
        self.client.force_login(self.users["approver1"])
        self.assertEqual(self.client.post("/api/pos/", {"number": "BLOCKED"}).status_code, 403)
        self.assertEqual(self.client.post("/", {"number": "BLOCKED"}).status_code, 403)

    def test_draft_owner_and_status_come_from_the_server(self):
        self.client.force_login(self.users["lead1"])
        response = self.client.post("/api/pos/", {
            "number": "po-new", "creator_id": self.users["creator2"].pk, "status": "SUBMITTED",
        }, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        order = PurchaseOrder.objects.get(pk=response.json()["id"])
        self.assertEqual((order.number, order.creator_id, order.status), ("PO-NEW", self.users["lead1"].pk, "DRAFT"))

    def test_supabase_public_roles_have_no_row_policies_on_server_data(self):
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT tablename, rowsecurity FROM pg_tables
                WHERE schemaname = current_schema()
                  AND tablename IN ('auth_user','auth_user_groups','django_session','orders_purchaseorder')
            """)
            flags = dict(cursor.fetchall())
        self.assertEqual(len(flags), 4)
        self.assertTrue(all(flags.values()))
