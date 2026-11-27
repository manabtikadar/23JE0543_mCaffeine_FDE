import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0003_lineitem_purchaseorder_pdf_key_purchaseorder_po_date_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='purchaseorder',
            name='status',
            field=models.CharField(choices=[('DRAFT', 'Draft'), ('SUBMITTED', 'Submitted'), ('REJECTED', 'Rejected'), ('APPROVED', 'Approved')], default='DRAFT', max_length=12),
        ),
        migrations.CreateModel(
            name='HistoryEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('SUBMIT', 'Submitted'), ('RESUBMIT', 'Resubmitted'), ('APPROVE', 'Approved'), ('REJECT', 'Rejected')], max_length=8)),
                ('recorded_at', models.DateTimeField(auto_now_add=True)),
                ('remark', models.TextField(blank=True)),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='history', to='orders.purchaseorder')),
            ],
            options={
                'ordering': ['pk'],
            },
        ),
        migrations.RunSQL("""
            ALTER TABLE orders_historyentry ENABLE ROW LEVEL SECURITY;
            CREATE FUNCTION orders_keep_history() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'Purchase order history is append-only';
            END;
            $$;
            CREATE TRIGGER orders_history_immutable BEFORE UPDATE OR DELETE ON orders_historyentry
            FOR EACH ROW EXECUTE FUNCTION orders_keep_history();
        """, """
            DROP TRIGGER orders_history_immutable ON orders_historyentry;
            DROP FUNCTION orders_keep_history();
        """),
    ]
