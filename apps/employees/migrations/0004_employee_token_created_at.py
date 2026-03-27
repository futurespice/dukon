# AUDIT-3 FIX #7: Add token_created_at to Employee for token TTL enforcement.
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0003_alter_employee_password'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='token_created_at',
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name='Токен выдан',
            ),
            preserve_default=False,
        ),
    ]
