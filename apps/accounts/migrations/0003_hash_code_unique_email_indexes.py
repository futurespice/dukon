from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_add_two_fa_purpose'),
    ]

    operations = [
        # -----------------------------------------------------------------------
        # HIGH FIX #10: Change VerificationCode.code from PositiveIntegerField
        # to CharField(64) to store HMAC-SHA256 digests instead of raw integers.
        #
        # All existing plaintext codes are immediately invalidated (is_used=True)
        # via RunSQL because they cannot be reverse-engineered into a valid hash.
        # Codes are short-lived (5 min TTL) so this causes minimal disruption.
        # -----------------------------------------------------------------------
        migrations.AlterField(
            model_name='verificationcode',
            name='code',
            field=models.CharField(max_length=64, verbose_name='Хэш кода'),
        ),
        # Invalidate all codes created before this migration — their stored values
        # are plain integers that will never match an HMAC digest.
        migrations.RunSQL(
            sql="UPDATE accounts_verificationcode SET is_used = TRUE WHERE is_used = FALSE",
            reverse_sql=migrations.RunSQL.noop,
        ),
        # -----------------------------------------------------------------------
        # HIGH FIX #11: Add a partial unique index on User.email so that no two
        # non-null, non-empty email addresses can coexist. NULL and '' are allowed
        # (phone-only users), but any real email must be globally unique.
        # -----------------------------------------------------------------------
        migrations.AddConstraint(
            model_name='user',
            constraint=models.UniqueConstraint(
                fields=['email'],
                condition=models.Q(email__isnull=False) & ~models.Q(email=''),
                name='unique_non_null_email',
            ),
        ),
        # -----------------------------------------------------------------------
        # Composite index on (phone, purpose, is_used) — used by
        # validate_verification_code() on every code check.
        # Index on expires_at — used in the filter expires_at__gt=now().
        # -----------------------------------------------------------------------
        migrations.AddIndex(
            model_name='verificationcode',
            index=models.Index(
                fields=['phone', 'purpose', 'is_used'],
                name='vc_phone_purpose_used_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='verificationcode',
            index=models.Index(
                fields=['expires_at'],
                name='vc_expires_at_idx',
            ),
        ),
    ]
