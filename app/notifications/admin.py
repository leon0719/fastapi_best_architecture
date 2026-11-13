"""Admin view for outbox notifications:查寄送狀態,不可新增或修改。"""

from sqladmin import ModelView

from app.notifications.models import OutboxNotification


class OutboxNotificationAdmin(ModelView, model=OutboxNotification):
    name = "Notification"
    name_plural = "Notifications"
    icon = "fa-solid fa-paper-plane"

    column_list = [
        OutboxNotification.id,
        OutboxNotification.channel,
        OutboxNotification.recipient,
        OutboxNotification.retry_count,
        OutboxNotification.sent_at,
        OutboxNotification.abandoned_at,
        OutboxNotification.created_at,
    ]
    column_details_list = [*column_list, OutboxNotification.last_error, OutboxNotification.next_attempt_at]
    column_searchable_list = [OutboxNotification.recipient]
    column_default_sort = [(OutboxNotification.id, True)]

    can_create = False
    can_edit = False
    can_delete = True
    can_view_details = True
