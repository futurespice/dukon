from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.common.mixins import validate_bulk_ids
from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer
from apps.notifications.filters import NotificationFilter


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = (IsAuthenticated,)
    filterset_class = NotificationFilter

    def get_queryset(self):
        # AUDIT N+1 FIX: explicit order_by guarantees stable pagination even
        # when multiple notifications share the same created_at timestamp.
        # Meta.ordering = ['-created_at'] is not stable under high concurrency
        # — PostgreSQL may return rows in a different order across pages.
        # The secondary '-id' sort breaks ties deterministically.
        return (
            Notification.objects
            .filter(user=self.request.user)
            .order_by('-created_at', '-id')
        )


class NotificationDetailView(generics.RetrieveAPIView):
    serializer_class = NotificationSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class NotificationMarkAsReadView(APIView):
    """POST /notifications/{pk}/mark_as_read/ — mark a single notification as read."""
    permission_classes = (IsAuthenticated,)

    def post(self, request, pk):
        updated = Notification.objects.filter(pk=pk, user=request.user).update(is_read=True)
        if not updated:
            return Response({'detail': 'Не найдено.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationMarkAllAsReadView(APIView):
    """POST /notifications/mark_all_as_read/ — mark every unread notification as read."""
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        updated = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'marked': updated}, status=status.HTTP_200_OK)


class NotificationUnreadCountView(APIView):
    """
    GET /notifications/unread-count/
    Returns the count of unread notifications for the authenticated user.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({'unread_count': count}, status=status.HTTP_200_OK)


class NotificationBulkMarkAsReadView(APIView):
    """
    POST /notifications/bulk-mark-read/
    Body: {"ids": [1, 2, 3]}
    Marks up to 500 notifications as read in a single UPDATE.
    """
    permission_classes = (IsAuthenticated,)

    _MAX_BULK_IDS = 500

    def post(self, request):
        ids, err = validate_bulk_ids(
            request.data,
            max_count=self._MAX_BULK_IDS,
            action='передать',
        )
        if err:
            return err
        updated = Notification.objects.filter(
            pk__in=ids,
            user=request.user,
            is_read=False,
        ).update(is_read=True)
        return Response({'marked': updated}, status=status.HTTP_200_OK)
