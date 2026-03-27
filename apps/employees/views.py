from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.db import transaction

from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from apps.common.mixins import validate_bulk_ids
from apps.employees.models import Employee
from apps.employees.serializers import EmployeeSerializer, EmployeeLoginSerializer
from apps.employees.filters import EmployeeFilter

# R-4: Per-username failed-login lockout (independent of IP-based throttling).
# ScopedRateThrottle protects by IP only; an attacker who knows a valid username
# can brute-force passwords from rotating IPs without hitting the IP rate limit.
# These constants add a second layer: per-account lockout after N failures.
_EMP_FAIL_PREFIX = 'emp_login_fail:'
_EMP_FAIL_MAX = 10       # lock after 10 consecutive failures
_EMP_FAIL_TTL = 3600     # lockout window: 1 hour (matches 'auth' throttle window)


class EmployeeListCreateView(generics.ListCreateAPIView):
    serializer_class = EmployeeSerializer
    permission_classes = (IsAuthenticated,)
    filterset_class = EmployeeFilter
    search_fields = ('first_name', 'last_name', 'username')

    def get_queryset(self):
        return Employee.objects.select_related('store').filter(
            store__admin_user=self.request.user
        )


class EmployeeMultipleDeleteView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        ids, err = validate_bulk_ids(request.data)
        if err:
            return err
        deleted_count, _ = Employee.objects.filter(
            pk__in=ids,
            store__admin_user=request.user,
        ).delete()
        return Response({'deleted': deleted_count}, status=status.HTTP_200_OK)


class EmployeeDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EmployeeSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return Employee.objects.select_related('store').filter(
            store__admin_user=self.request.user
        )


class EmployeeLoginView(APIView):
    """POST /employees/auth/login/ — authenticate via username+password → UUID token."""
    permission_classes = ()
    authentication_classes = ()
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'

    # Constant-time dummy hash used when the employee is not found,
    # preventing timing-based username enumeration attacks.
    _DUMMY_HASH = 'pbkdf2_sha256$600000$dummy$aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa='

    def post(self, request):
        serializer = EmployeeLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data['username']
        raw_password = serializer.validated_data['password']

        # R-4 FIX (Brute-force protection per employee account):
        # Check the per-username lockout counter BEFORE any DB hit or
        # password computation. This is purely cache-based and fast.
        fail_key = f'{_EMP_FAIL_PREFIX}{username}'
        fail_count = cache.get(fail_key, 0)
        if fail_count >= _EMP_FAIL_MAX:
            return Response(
                {
                    'detail': (
                        'Аккаунт заблокирован из-за превышения количества попыток входа. '
                        'Попробуйте через 1 час.')
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            employee = Employee.objects.select_related('store').get(
                username=username, is_active=True
            )
        except Employee.DoesNotExist:
            # Always run check_password even on a miss to keep response time
            # constant and prevent timing-based username enumeration.
            check_password(raw_password, self._DUMMY_HASH)
            # Increment failure counter even for unknown usernames so that
            # an attacker can't distinguish 'wrong username' from 'wrong
            # password' via the lockout behaviour (i.e. unknown usernames
            # never lock = confirm they don't exist).
            cache.add(fail_key, 0, timeout=_EMP_FAIL_TTL)
            cache.incr(fail_key)
            return Response(
                {'detail': 'Неверный логин или пароль.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # FIX #4 (CRITICAL): Employee.password is nullable (null=True, blank=True).
        # Calling check_password(raw, None) raises AttributeError: 'NoneType' has
        # no attribute 'split' → uncaught → 500 Internal Server Error.
        # Guard: treat a missing password hash as an authentication failure.
        if not employee.password or not check_password(raw_password, employee.password):
            # R-4: atomic increment of the per-username failure counter.
            # cache.add() is SETNX — sets key only if absent (with TTL).
            # cache.incr() is atomic INCR — safe under concurrency.
            cache.add(fail_key, 0, timeout=_EMP_FAIL_TTL)
            cache.incr(fail_key)
            return Response(
                {'detail': 'Неверный логин или пароль.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # M-6 FIX (Employee token overwrite on concurrent logins):
        # Employee has a SINGLE token column. With select_for_update() the
        # writes are serialised, but the second request still overwrites the
        # first token in the DB — client A received token_A which is now
        # invalid because client B saved token_B on top.
        #
        # Minimal fix: reuse the existing token if it is still within its TTL.
        # Concurrent logins by the same employee share the same token until it
        # expires or the employee explicitly logs out (which rotates the token).
        # This is safe because:
        #   - logout already calls refresh_token() to invalidate the token.
        #   - is_token_valid() checks token_created_at + EMPLOYEE_TOKEN_TTL_HOURS.
        #   - select_for_update() still serialises the check+save so no two
        #     requests can race on the is_token_valid() read.
        # R-4: successful login clears the failure counter so the account
        # is not permanently locked after an operator resets the password.
        cache.delete(fail_key)

        with transaction.atomic():
            locked_employee = Employee.objects.select_for_update().get(pk=employee.pk)
            if not locked_employee.is_token_valid():
                # Token expired or never set — generate a fresh one.
                locked_employee.refresh_token()
            # If the token is still valid, return it as-is (idempotent login).

        return Response(
            {'token': str(locked_employee.token), **EmployeeSerializer(locked_employee).data},
            status=status.HTTP_200_OK,
        )


class EmployeeLogoutView(APIView):
    """
    POST /employees/auth/logout/
    Accepts the UUID session token in the request body.
    Rotates the token so the old value immediately becomes invalid.
    """
    permission_classes = ()
    authentication_classes = ()
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'

    def post(self, request):
        token = request.data.get('token')
        if not token:
            return Response(
                {'detail': 'Поле token обязательно.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            employee = Employee.objects.get(token=token, is_active=True)
        except Employee.DoesNotExist:
            return Response(
                {'detail': 'Токен не найден или уже инвалидирован.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not employee.is_token_valid():
            return Response(
                {'detail': 'Токен истёк. Войдите заново.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        employee.refresh_token()
        return Response({'detail': 'Выход выполнен. Токен инвалидирован.'}, status=status.HTTP_200_OK)
