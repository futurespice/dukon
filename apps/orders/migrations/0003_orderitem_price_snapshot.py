"""
Migration: Add price_at_order and product_name_at_order to OrderItem.
Also changes product FK to SET_NULL and quantity to PositiveIntegerField
to properly support order history after product deletion.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_rename_notifications_sent'),
        ('products', '0001_initial'),
    ]

    operations = [
        # Add snapshot price field
        migrations.AddField(
            model_name='orderitem',
            name='price_at_order',
            field=models.DecimalField(
                decimal_places=2,
                max_digits=12,
                verbose_name='Цена на момент заказа',
                help_text='Фиксируется автоматически из ProductModel.price при создании заказа.',
                default=0,
            ),
            preserve_default=False,
        ),
        # Add snapshot product name field
        migrations.AddField(
            model_name='orderitem',
            name='product_name_at_order',
            field=models.CharField(
                max_length=512,
                verbose_name='Название продукта на момент заказа',
                help_text='Фиксируется автоматически для сохранения истории.',
                default='',
            ),
            preserve_default=False,
        ),
        # Back-fill existing rows: copy price and name from related ProductModel
        migrations.RunSQL(
            sql="""
                UPDATE orders_orderitem oi
                SET
                    price_at_order      = COALESCE(pm.price, 0),
                    product_name_at_order = COALESCE(pm.name, 'Unknown')
                FROM products_productmodel pm
                WHERE oi.product_id = pm.id;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Change product FK to SET_NULL so history survives product deletion
        migrations.AlterField(
            model_name='orderitem',
            name='product',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='order_items',
                to='products.productmodel',
                verbose_name='Продукт',
            ),
        ),
        # Change quantity to PositiveIntegerField (was PositiveBigIntegerField)
        migrations.AlterField(
            model_name='orderitem',
            name='quantity',
            field=models.PositiveIntegerField(
                default=1,
                verbose_name='Количество',
            ),
        ),
    ]
