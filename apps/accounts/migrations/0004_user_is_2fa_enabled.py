from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_hash_code_unique_email_indexes'),
    ]

    operations = [
        # MEDIUM FIX #15: per-user 2FA toggle.
        # Defaults to False so all existing users keep the current single-step
        # login behaviour until they explicitly enable 2FA.
        migrations.AddField(
            model_name='user',
            name='is_2fa_enabled',
            field=models.BooleanField(
                default=False,
                verbose_name='2FA включена',
                help_text='Если включено, каждый вход требует подтверждения через WhatsApp.',
            ),
        ),
    ]
