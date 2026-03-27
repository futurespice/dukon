"""Migration: rename sended_notifications → notifications_sent (db_column preserved)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0001_initial'),
    ]

    operations = [
        # Step 1: rename at Django level (no DB change — column stays 'sended_notifications')
        migrations.RenameField(
            model_name='order',
            old_name='sended_notifications',
            new_name='notifications_sent',
        ),
        # Step 2: add db_column so Django keeps pointing at the original column name
        migrations.AlterField(
            model_name='order',
            name='notifications_sent',
            field=models.BooleanField(
                db_column='sended_notifications',
                default=False,
                verbose_name='Уведомления отправлены',
            ),
        ),
    ]
