import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0003_alter_favoriteproduct_options'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # SMALL FIX #22: track the uploader of each Photo so that mutations
        # (PUT/PATCH/DELETE) can be scoped to the owner, preventing any
        # authenticated user from modifying photos they didn't upload.
        migrations.AddField(
            model_name='photo',
            name='uploaded_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='uploaded_photos',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Загрузил',
            ),
        ),
        # MEDIUM FIX #19: composite index for the common store+hidden product filter.
        migrations.AddIndex(
            model_name='product',
            index=models.Index(
                fields=['store', 'is_hidden'],
                name='product_store_hidden_idx',
            ),
        ),
    ]
