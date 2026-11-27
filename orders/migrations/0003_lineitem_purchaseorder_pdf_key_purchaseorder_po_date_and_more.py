import django.db.models.deletion
import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_protect_server_tables'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LineItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sku', models.CharField(max_length=64)),
                ('description', models.CharField(max_length=500)),
                ('quantity', models.PositiveIntegerField()),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=14)),
                ('line_total', models.DecimalField(decimal_places=2, max_digits=16)),
            ],
        ),
        migrations.AddField(
            model_name='purchaseorder',
            name='pdf_key',
            field=models.CharField(blank=True, editable=False, max_length=160),
        ),
        migrations.AddField(
            model_name='purchaseorder',
            name='po_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='purchaseorder',
            name='printed_total',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=16, null=True),
        ),
        migrations.AddField(
            model_name='purchaseorder',
            name='vendor',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddConstraint(
            model_name='purchaseorder',
            constraint=models.UniqueConstraint(django.db.models.functions.text.Upper(django.db.models.functions.text.Trim('number')), name='po_normalized_number_unique'),
        ),
        migrations.AddField(
            model_name='lineitem',
            name='order',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='orders.purchaseorder'),
        ),
        migrations.RunSQL("ALTER TABLE orders_lineitem ENABLE ROW LEVEL SECURITY", migrations.RunSQL.noop),
    ]
