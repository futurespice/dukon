from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    """Custom manager — phone is the unique identifier instead of username."""

    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError('Номер телефона обязателен')
        extra_fields.setdefault('is_active', True)
        # Use the enum value via the model import to avoid hardcoded strings.
        from apps.accounts.models import User as _User
        extra_fields.setdefault('role', _User.Role.NOT_VERIFIED)
        user = self.model(phone=phone, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        from apps.accounts.models import User as _User
        extra_fields.setdefault('role', _User.Role.ADMIN)
        extra_fields.setdefault('is_active', True)

        if not extra_fields.get('is_staff'):
            raise ValueError('Superuser must have is_staff=True.')
        if not extra_fields.get('is_superuser'):
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(phone, password, **extra_fields)
