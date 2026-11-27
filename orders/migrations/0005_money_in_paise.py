from django.db import migrations, models


def convert(table, name, digits, nullable=False):
    column = f"{name}_paise"
    return migrations.SeparateDatabaseAndState(
        database_operations=[migrations.RunSQL(
            f"ALTER TABLE {table} ALTER COLUMN {name} TYPE bigint USING ({name} * 100)::bigint;"
            f"ALTER TABLE {table} RENAME COLUMN {name} TO {column};",
            f"ALTER TABLE {table} RENAME COLUMN {column} TO {name};"
            f"ALTER TABLE {table} ALTER COLUMN {name} TYPE numeric({digits},2) USING {name}::numeric / 100;",
        )],
        state_operations=[migrations.AlterField(
            model_name=table.removeprefix("orders_"), name=name,
            field=models.BigIntegerField(db_column=column, null=nullable, blank=nullable),
        )],
    )


class Migration(migrations.Migration):
    dependencies = [("orders", "0004_approval_history")]
    operations = [
        convert("orders_purchaseorder", "printed_total", 16, nullable=True),
        convert("orders_lineitem", "unit_price", 14),
        convert("orders_lineitem", "line_total", 16),
    ]
