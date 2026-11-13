"""Admin view for User model."""

from wtforms import SelectField

from app.audit.admin import AdminAuditMixin
from app.users.models import Role, User


class UserAdmin(AdminAuditMixin, model=User):
    """Admin view for managing users. 新增/修改/刪除會寫進稽核軌跡(AdminAuditMixin)。"""

    # Model metadata
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"

    # Column configuration
    column_list = [User.id, User.name, User.email, User.role, User.is_active, User.created_at]
    column_searchable_list = [User.name, User.email]
    column_sortable_list = [User.id, User.name, User.created_at]

    # Form configuration:角色用下拉選單,只能選 Role 定義的值
    form_columns = [User.name, User.email, User.role, User.is_active]
    form_overrides = {"role": SelectField}
    form_args = {"role": {"choices": [(r.value, r.value) for r in Role], "default": Role.USER.value}}

    # Permissions
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True

    # Pagination
    page_size = 50
    page_size_options = [25, 50, 100, 200]
