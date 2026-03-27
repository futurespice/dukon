from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0004_fix_coords_and_slide_urls'),
    ]

    operations = [
        # SMALL FIX #21: rename Slide.ordering → Slide.sort_order.
        # Step 1: rename the Python field (Django would rename the DB column too,
        # but Step 2 adds db_column='ordering' to keep the existing column name,
        # so no actual ALTER TABLE occurs in PostgreSQL).
        migrations.RenameField(
            model_name='slide',
            old_name='ordering',
            new_name='sort_order',
        ),
        # Step 2: add db_column so the column stays named 'ordering' in the DB.
        # This reverses the column rename Django would otherwise apply, keeping
        # the migration backward-compatible with any existing data or indexes.
        migrations.AlterField(
            model_name='slide',
            name='sort_order',
            field=models.PositiveIntegerField(
                default=0,
                verbose_name='Порядок',
                db_column='ordering',
            ),
        ),
    ]
