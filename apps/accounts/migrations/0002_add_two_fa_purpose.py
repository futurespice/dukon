from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='verificationcode',
            name='purpose',
            field=models.CharField(
                choices=[
                    ('REGISTER', 'Регистрация'),
                    ('RESET_PASSWORD', 'Сброс пароля'),
                    ('PHONE_CHANGE', 'Смена телефона'),
                    ('TWO_FA', 'Двухфакторная аутентификация'),
                ],
                default='REGISTER',
                max_length=20,
                verbose_name='Назначение',
            ),
        ),
    ]
