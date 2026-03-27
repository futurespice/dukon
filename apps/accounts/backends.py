from django.contrib.auth.backends import ModelBackend
from apps.accounts.models import User


class PhoneBackend(ModelBackend):
    """Authenticate using phone + password instead of username + password."""

    def authenticate(self, request, phone=None, password=None, **kwargs):
        if phone is None or password is None:
            return None
        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            # AUDIT-3 NEW FIX: Run check_password against a dummy hash to
            # prevent timing-based phone enumeration. Without this, a miss
            # returns ~instantly while a hit takes ~200ms (bcrypt), revealing
            # whether the phone is registered.
            from django.contrib.auth.hashers import check_password
            check_password(password, 'pbkdf2_sha256$600000$dummy$hash')
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
