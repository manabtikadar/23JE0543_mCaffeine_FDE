from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MoneyMigrationTests(TransactionTestCase):
    def test_existing_rupees_convert_exactly_and_reverse(self):
        before = [("orders", "0004_approval_history")]
        after = [("orders", "0005_money_in_paise")]

        def migrate(target):
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            return executor.loader.project_state(target).apps

        old = migrate(before)
        self.addCleanup(migrate, after)
        owner = old.get_model("auth", "User").objects.create(username="migration-owner")
        po = old.get_model("orders", "PurchaseOrder").objects.create(
            creator=owner, number="MIGRATION-1", printed_total=Decimal("245.50"))
        line = old.get_model("orders", "LineItem").objects.create(
            order=po, sku="MC", description="Sample", quantity=2,
            unit_price=Decimal("122.75"), line_total=Decimal("245.50"))
        new = migrate(after)
        self.assertEqual(new.get_model("orders", "PurchaseOrder").objects.get(pk=po.pk).printed_total, 24550)
        migrated = new.get_model("orders", "LineItem").objects.get(pk=line.pk)
        self.assertEqual((migrated.unit_price, migrated.line_total), (12275, 24550))
        old = migrate(before)
        self.assertEqual(old.get_model("orders", "LineItem").objects.get(pk=line.pk).unit_price, Decimal("122.75"))
