"""
Migration: fix products audit issues
- Product.uuid: remove null/blank, add unique=True
- Category.uuid: add unique=True
- Product.article: keep DB column 'acrticul', rename Python attr
"""
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0001_initial'),
    ]

    operations = [
        # --- Product.uuid: unique, non-null ---
        migrations.AlterField(
            model_name='product',
            name='uuid',
            field=models.UUIDField(
                default=uuid.uuid4,
                unique=True,
                verbose_name='UUID',
            ),
        ),
        # --- Category.uuid: add unique constraint ---
        migrations.AlterField(
            model_name='category',
            name='uuid',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                verbose_name='UUID',
            ),
        ),
        # --- Product: rename acrticul → article at Django level ---
        migrations.RenameField(
            model_name='product',
            old_name='acrticul',
            new_name='article',
        ),
        # --- Product.article: add db_column to keep pointing at 'acrticul' column ---
        migrations.AlterField(
            model_name='product',
            name='article',
            field=models.CharField(
                blank=True,
                db_column='acrticul',
                max_length=255,
                null=True,
                verbose_name='Артикул',
            ),
        ),
    ]
