"""Admin view for AuthToken:只能看與刪除(刪除 = 強制登出),看不到 digest。"""

from sqladmin import ModelView

from app.auth.models import AuthToken


class AuthTokenAdmin(ModelView, model=AuthToken):
    """登入 token。刪除一筆 session 即撤銷該裝置的登入。"""

    name = "Auth Token"
    name_plural = "Auth Tokens"
    icon = "fa-solid fa-key"

    column_list = [AuthToken.id, AuthToken.user, AuthToken.kind, AuthToken.expires_at, AuthToken.created_at]
    column_details_list = column_list
    column_sortable_list = [AuthToken.id, AuthToken.expires_at, AuthToken.created_at]
    column_default_sort = [(AuthToken.id, True)]

    can_create = False
    can_edit = False
    can_delete = True
    can_view_details = True
