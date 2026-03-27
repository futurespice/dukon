"""Migration: fix Employee.position choices ACCOUNTAT → ACCOUNTANT."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0001_initial'),
    ]

    operations = [
        # Data migration: update existing rows
        migrations.RunSQL(
            sql="UPDATE employees_employee SET position = 'ACCOUNTANT' WHERE position = 'ACCOUNTAT';",
            reverse_sql="UPDATE employees_employee SET position = 'ACCOUNTAT' WHERE position = 'ACCOUNTANT';",
        ),
        migrations.AlterField(
            model_name='employee',
            name='position',
            field=models.CharField(
                choices=[
                    ('WAITER', 'Официант'),
                    ('ACCOUNTANT', 'Бухгалтер'),
                    ('CASHIER', 'Кассир'),
                ],
                max_length=20,
                verbose_name='Должность сотрудника',
            ),
        ),
    ]
