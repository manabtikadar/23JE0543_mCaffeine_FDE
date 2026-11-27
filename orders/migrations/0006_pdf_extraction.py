from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0005_money_in_paise'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseorder',
            name='extraction_method',
            field=models.CharField(choices=[('manual', 'Manual entry'), ('text_layer', 'PDF text layer'), ('unreadable', 'Manual entry (unreadable text layer)')], default='manual', max_length=16),
        ),
        migrations.AlterField(
            model_name='purchaseorder',
            name='number',
            field=models.CharField(max_length=64, null=True, unique=True),
        ),
    ]
