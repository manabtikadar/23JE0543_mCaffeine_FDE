from django.db import migrations


# Django connects as the table owner. Supabase's public API roles get no row policies.
SERVER_TABLES = (
    "auth_group", "auth_group_permissions", "auth_permission", "auth_user",
    "auth_user_groups", "auth_user_user_permissions", "django_content_type",
    "django_migrations", "django_session", "orders_purchaseorder",
)


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("sessions", "0001_initial"),
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY',
            # Keep existing accounts and sessions private even on application rollback.
            reverse_sql=migrations.RunSQL.noop,
        )
        for table in SERVER_TABLES
    ]
