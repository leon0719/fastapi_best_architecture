"""Admin view for User model."""

from sqladmin import ModelView

from app.users.models import User


class UserAdmin(ModelView, model=User):
    """Admin view for managing users."""

    # Model metadata
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"

    # Column configuration
    column_list = [User.id, User.name]
    column_searchable_list = [User.name]
    column_sortable_list = [User.id, User.name]

    # Form configuration
    form_columns = [User.name]

    # Permissions
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True

    # Pagination
    page_size = 50
    page_size_options = [25, 50, 100, 200]
