from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from apps.common.models import TimeStampedModel
from apps.accounts.managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model.
    Unique identifier: phone number.
    Roles: ADMIN | CLIENT | MANG (manager) | NOTVERIFY
    """

    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Администратор'
        CLIENT = 'CLIENT', 'Клиент'
        MANAGER = 'MANG', 'Менеджер'
        NOT_VERIFIED = 'NOTVERIFY', 'Не верифицирован'

    class Gender(models.TextChoices):
        MALE = 'M', 'Мужской'
        FEMALE = 'W', 'Женский'
        OTHER = 'OTHER', 'Другой'
        NONE = 'NONE', 'Не указан'

    phone = models.CharField(
        max_length=128,
        unique=True,
        verbose_name='Телефон',
    )
    email = models.EmailField(
        null=True,
        blank=True,
        verbose_name='Эл.почта',
    )
    first_name = models.CharField(max_length=150, blank=True, verbose_name='Имя')
    last_name = models.CharField(max_length=150, blank=True, verbose_name='Фамилия')
    middle_name = models.CharField(
        max_length=255, null=True, blank=True, verbose_name='Отчество'
    )
    image = models.ImageField(
        upload_to='users/avatars/',
        null=True,
        blank=True,
        verbose_name='Фото',
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.NOT_VERIFIED,
        verbose_name='Role',
    )
    gender = models.CharField(
        max_length=10,
        choices=Gender.choices,
        default=Gender.NONE,
        verbose_name='Пол',
    )
    date_of_birth = models.DateField(null=True, blank=True, verbose_name='Дата рождения')
    date_joined = models.DateTimeField(auto_now_add=True, verbose_name='Дата регистрации')
    last_activity = models.DateTimeField(null=True, blank=True, verbose_name='Last')

    # MEDIUM FIX #15: per-user 2FA flag.
    # When True, POST /accounts/login/ triggers a WhatsApp code instead of
    # issuing JWT tokens directly. Defaults to False so existing users are
    # unaffected until they opt in.
    is_2fa_enabled = models.BooleanField(
        default=False,
        verbose_name='2FA включена',
        help_text='Если включено, каждый вход требует подтверждения через WhatsApp.',
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name='Активный',
        help_text='Отметьте, если пользователь должен считаться активным. '
                  'Уберите эту отметку вместо удаления учётной записи.',
    )
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'
        ordering = ['-date_joined']
        constraints = [
            models.UniqueConstraint(
                fields=['email'],
                condition=models.Q(email__isnull=False) & ~models.Q(email=''),
                name='unique_non_null_email',
            ),
        ]

    def __str__(self):
        return self.get_full_name() or self.phone

    def get_full_name(self):
        parts = filter(None, [self.last_name, self.first_name, self.middle_name])
        return ' '.join(parts)


class UserBonusCard(TimeStampedModel):
    """Bonus card assigned to a user. One card per user."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='bonus_card',
        verbose_name='Пользователь',
    )
    bonus_card_number = models.CharField(
        max_length=20,
        unique=True,
        verbose_name='Bonus card number',
    )

    class Meta:
        verbose_name = 'Бонусная карта пользователя'
        verbose_name_plural = 'Бонусные карты пользователей'

    def __str__(self):
        return f'{self.user} — {self.bonus_card_number}'


class VerificationCode(TimeStampedModel):
    """
    SMS / phone verification code.
    Used for registration, reset-password, phone-number change, and 2FA flows.

    HIGH FIX #10: The 'code' field now stores an HMAC-SHA256 digest instead of the
    raw 4-digit integer. Since there are only 9 000 possible codes, storing the
    plain value enables trivial precomputation attacks on a compromised DB.
    """

    class Purpose(models.TextChoices):
        REGISTER = 'REGISTER', 'Регистрация'
        RESET_PASSWORD = 'RESET_PASSWORD', 'Сброс пароля'
        PHONE_CHANGE = 'PHONE_CHANGE', 'Смена телефона'
        TWO_FA = 'TWO_FA', 'Двухфакторная аутентификация'

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='verification_codes',
        null=True,
        blank=True,
        verbose_name='Пользователь',
    )
    idempotency_key = models.CharField(
        max_length=255, null=True, blank=True, unique=True,
        verbose_name='Ключ идемпотентности'
    )
    phone = models.CharField(max_length=128, verbose_name='Телефон')
    code = models.CharField(max_length=64, verbose_name='Хэш кода')
    purpose = models.CharField(
        max_length=20,
        choices=Purpose.choices,
        default=Purpose.REGISTER,
        verbose_name='Назначение',
    )
    is_used = models.BooleanField(default=False, verbose_name='Использован')
    expires_at = models.DateTimeField(verbose_name='Истекает')

    class Meta:
        verbose_name = 'Код верификации'
        verbose_name_plural = 'Коды верификации'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['phone', 'purpose', 'is_used'], name='vc_phone_purpose_used_idx'),
            models.Index(fields=['expires_at'], name='vc_expires_at_idx'),
        ]

    def __str__(self):
        return f'{self.phone} — ****** ({self.purpose})'
