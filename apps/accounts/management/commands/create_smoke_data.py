"""
Management command: create_smoke_data
======================================
Создаёт минимальный набор данных для запуска smoke-тестов через Newman/Postman.

Использование:
    python manage.py create_smoke_data           # создаёт или обновляет данные
    python manage.py create_smoke_data --reset   # удаляет и создаёт заново

Что создаётся:
    User    phone=+996700000001  password=SmokePass123!  role=CLIENT  2fa=False
    Store   name="Smoke Store"  slug="smoke-store-001"  (admin_user=smoke user)
    Category "Smoke Category"
    Product "Smoke Product" + ProductModel  (quantity=50, price=500.00)
    Employee  username="smoke_employee"  password=EmpPass123!

После выполнения Newman сам сохранит store_uuid / product_id / order_id
через post-response скрипты коллекции.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

SMOKE_PHONE = '+996700000001'
SMOKE_PASSWORD = 'SmokePass123!'
SMOKE_EMPLOYEE_USERNAME = 'smoke_employee'
SMOKE_EMPLOYEE_PASSWORD = 'EmpPass123!'


class Command(BaseCommand):
    help = 'Create smoke test fixtures (user, store, product, employee)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing smoke data before creating fresh records',
        )

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model
        from apps.stores.models import Store
        from apps.products.models import Product, ProductModel, Category
        from apps.employees.models import Employee

        User = get_user_model()

        if options['reset']:
            self.stdout.write('Deleting existing smoke data...')
            User.objects.filter(phone=SMOKE_PHONE).delete()
            Store.objects.filter(slug='smoke-store-001').delete()
            Employee.objects.filter(username=SMOKE_EMPLOYEE_USERNAME).delete()
            self.stdout.write(self.style.WARNING('Smoke data deleted.'))

        with transaction.atomic():
            # ── Main smoke user ───────────────────────────────────────────
            user, created = User.objects.get_or_create(
                phone=SMOKE_PHONE,
                defaults={
                    'first_name': 'Smoke',
                    'last_name': 'User',
                    'is_active': True,
                    'is_2fa_enabled': False,
                },
            )
            user.set_password(SMOKE_PASSWORD)
            user.is_2fa_enabled = False
            user.is_active = True
            if hasattr(User, 'Role'):
                user.role = User.Role.CLIENT
                user.save(update_fields=['password', 'is_2fa_enabled', 'is_active', 'role'])
            else:
                user.save(update_fields=['password', 'is_2fa_enabled', 'is_active'])

            verb = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(f'{verb} user: {SMOKE_PHONE}'))

            # ── Smoke store ───────────────────────────────────────────────
            # Store uses admin_user (not owner), address is required
            store, s_created = Store.objects.get_or_create(
                slug='smoke-store-001',
                defaults={
                    'admin_user': user,
                    'name': 'Smoke Store',
                    'address': 'ул. Тестовая 1, Бишкек',
                    'description': 'Auto-generated smoke test store',
                },
            )
            if not s_created and store.admin_user_id != user.pk:
                store.admin_user = user
                store.save(update_fields=['admin_user'])

            verb = 'Created' if s_created else 'Exists'
            self.stdout.write(self.style.SUCCESS(
                f'{verb} store: {store.uuid} (slug={store.slug})'
            ))

            # ── Category ──────────────────────────────────────────────────
            category, _ = Category.objects.get_or_create(
                store=store,
                name='Smoke Category',
                defaults={'parent': None},
            )

            # ── Product ───────────────────────────────────────────────────
            # short_description is required (max 255)
            product, p_created = Product.objects.get_or_create(
                store=store,
                name='Smoke Product',
                defaults={
                    'short_description': 'Smoke test product',
                    'description': 'Auto-generated smoke test product',
                    'category': category,
                    'is_hidden': False,
                },
            )
            verb = 'Created' if p_created else 'Exists'
            self.stdout.write(self.style.SUCCESS(f'{verb} product: id={product.id}'))

            # ── ProductModel (variant) ────────────────────────────────────
            pm, pm_created = ProductModel.objects.get_or_create(
                product=product,
                defaults={
                    'name': 'Стандарт',
                    'price': '500.00',
                    'quantity': 50,
                },
            )
            if pm.quantity < 10:
                pm.quantity = 50
                pm.save(update_fields=['quantity'])

            verb = 'Created' if pm_created else 'Exists'
            self.stdout.write(self.style.SUCCESS(
                f'{verb} ProductModel: id={pm.id} price={pm.price} qty={pm.quantity}'
            ))

            # ── Employee ──────────────────────────────────────────────────
            # Employee model: username, password (hashed), first_name,
            # last_name, position, store — no phone field
            try:
                employee, e_created = Employee.objects.get_or_create(
                    username=SMOKE_EMPLOYEE_USERNAME,
                    defaults={
                        'store': store,
                        'first_name': 'Smoke',
                        'last_name': 'Employee',
                        'position': Employee.Position.CASHIER,
                    },
                )
                # Always reset password so login tests work
                from django.contrib.auth.hashers import make_password
                employee.password = make_password(SMOKE_EMPLOYEE_PASSWORD)
                employee.store = store
                employee.save(update_fields=['password', 'store'])

                verb = 'Created' if e_created else 'Updated'
                self.stdout.write(self.style.SUCCESS(
                    f'{verb} employee: id={employee.id} username={employee.username}'
                ))
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f'Could not create employee: {exc}'))

        # ── Summary ───────────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✅  Smoke data ready!'))
        self.stdout.write('')
        self.stdout.write('Login credentials for Newman / Postman:')
        self.stdout.write(f'  phone    : {SMOKE_PHONE}')
        self.stdout.write(f'  password : {SMOKE_PASSWORD}')
        self.stdout.write(f'  store_uuid   : {store.uuid}')
        self.stdout.write(f'  product_id   : {product.id}')
        self.stdout.write(f'  product_model: {pm.id}')
        self.stdout.write(f'  emp_username : {SMOKE_EMPLOYEE_USERNAME}')
        self.stdout.write(f'  emp_password : {SMOKE_EMPLOYEE_PASSWORD}')
        self.stdout.write('')
        self.stdout.write('Run smoke tests:')
        self.stdout.write('  ./run_tests.sh smoke')
        self.stdout.write('')
        self.stdout.write('Reset + recreate:')
        self.stdout.write('  python manage.py create_smoke_data --reset')
