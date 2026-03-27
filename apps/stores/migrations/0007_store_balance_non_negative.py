# Generated manually — M-4 FIX: non-negative balance CHECK constraint on Store.
# Protects against balance going negative via admin, raw SQL, or any future
# code path that bypasses stores.services.purchase_tariff().

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0006_alter_slide_options'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='store',
            constraint=models.CheckConstraint(
                condition=models.Q(balance__gte=0),
                name='store_balance_non_negative',
            ),
        ),
    ]
