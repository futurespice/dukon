"""Migration: fix stores audit issues — IN_PROCCESSING → IN_PROCESSING, add StoreBankDetail view support."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0001_initial'),
    ]

    operations = [
        # Data migration: fix existing typo in status column
        migrations.RunSQL(
            sql="""
                UPDATE stores_storebalancetransaction
                SET status = 'IN_PROCESSING'
                WHERE status = 'IN_PROCCESSING';
            """,
            reverse_sql="""
                UPDATE stores_storebalancetransaction
                SET status = 'IN_PROCCESSING'
                WHERE status = 'IN_PROCESSING';
            """,
        ),
        # Update field choices
        migrations.AlterField(
            model_name='storebalancetransaction',
            name='status',
            field=models.CharField(
                choices=[
                    ('SUCCESS', 'Успешно'),
                    ('FAILURE', 'Ошибка'),
                    ('IN_PROCESSING', 'В обработке'),
                ],
                default='IN_PROCESSING',
                max_length=20,
                verbose_name='Статус',
            ),
        ),
    ]
