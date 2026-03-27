"""
Smoke tests for the notifications app.
"""
import pytest
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User
from apps.accounts.services import create_bonus_card_for_user
from apps.notifications.models import Notification


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user(db):
    u = User.objects.create_user(
        phone='+996733000001',
        password='pass12345',
        role=User.Role.CLIENT,
    )
    create_bonus_card_for_user(u)
    return u


@pytest.fixture
def notifications(db, user):
    return [
        Notification.objects.create(user=user, title=f'Notif {i}', is_read=False)
        for i in range(5)
    ]


@pytest.mark.django_db
def test_list_requires_auth(client):
    resp = client.get('/api/v1/notifications/')
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_mark_all_as_read(client, user, notifications):
    """POST /notifications/mark_all_as_read/ marks all as read, returns count."""
    client.force_authenticate(user=user)
    resp = client.post('/api/v1/notifications/mark_all_as_read/')
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()['marked'] == 5
    assert Notification.objects.filter(user=user, is_read=False).count() == 0


@pytest.mark.django_db
def test_bulk_mark_as_read(client, user, notifications):
    """POST /notifications/bulk-mark-read/ marks selected IDs only."""
    client.force_authenticate(user=user)
    ids = [notifications[0].pk, notifications[1].pk]
    resp = client.post('/api/v1/notifications/bulk-mark-read/', {'ids': ids}, format='json')
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()['marked'] == 2
    assert Notification.objects.filter(user=user, is_read=False).count() == 3


@pytest.mark.django_db
def test_bulk_mark_empty_ids(client, user):
    """Empty ids list returns 400."""
    client.force_authenticate(user=user)
    resp = client.post('/api/v1/notifications/bulk-mark-read/', {'ids': []}, format='json')
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_bulk_mark_other_user_notifications_untouched(client, db, user, notifications):
    """User can only mark their own notifications."""
    other = User.objects.create_user(
        phone='+996733000099', password='pass', role=User.Role.CLIENT,
    )
    other_notif = Notification.objects.create(user=other, title='Other', is_read=False)

    client.force_authenticate(user=user)
    resp = client.post(
        '/api/v1/notifications/bulk-mark-read/',
        {'ids': [other_notif.pk]},
        format='json',
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()['marked'] == 0  # nothing marked — wrong user
    other_notif.refresh_from_db()
    assert other_notif.is_read is False
