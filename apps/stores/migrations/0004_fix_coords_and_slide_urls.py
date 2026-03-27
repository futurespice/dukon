from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0003_rename_banketype_banktype_alter_store_balance_and_more'),
    ]

    operations = [
        # latitude: CharField → DecimalField with coordinate validators
        migrations.AlterField(
            model_name='store',
            name='latitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
                validators=[
                    MinValueValidator(-90),
                    MaxValueValidator(90),
                ],
                verbose_name='Широта',
            ),
        ),
        # longitude: CharField → DecimalField with coordinate validators
        migrations.AlterField(
            model_name='store',
            name='longitude',
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
                validators=[
                    MinValueValidator(-180),
                    MaxValueValidator(180),
                ],
                verbose_name='Долгота',
            ),
        ),
        # button_web_url: CharField → URLField
        migrations.AlterField(
            model_name='slide',
            name='button_web_url',
            field=models.URLField(
                blank=True,
                max_length=255,
                null=True,
                verbose_name='URL для веб-кнопки',
            ),
        ),
        # button_mob_url: CharField → URLField
        migrations.AlterField(
            model_name='slide',
            name='button_mob_url',
            field=models.URLField(
                blank=True,
                max_length=255,
                null=True,
                verbose_name='URL для мобильной версии',
            ),
        ),
    ]
