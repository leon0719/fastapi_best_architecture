"""Admin view for Chatbot model."""

from sqladmin import ModelView

from app.chatbots.models import Chatbot


class ChatbotAdmin(ModelView, model=Chatbot):
    """Admin view for managing chatbots."""

    # Model metadata
    name = "Chatbot"
    name_plural = "Chatbots"
    icon = "fa-solid fa-robot"

    # Column configuration
    column_list = [
        Chatbot.id,
        Chatbot.name,
        Chatbot.description,
        Chatbot.is_active,
        Chatbot.created_at,
        Chatbot.updated_at,
    ]
    column_searchable_list = [Chatbot.name, Chatbot.description]
    column_sortable_list = [
        Chatbot.id,
        Chatbot.name,
        Chatbot.is_active,
        Chatbot.created_at,
        Chatbot.updated_at,
    ]
    column_default_sort = ("created_at", True)  # Sort by created_at DESC

    # Form configuration
    form_columns = [
        Chatbot.name,
        Chatbot.description,
        Chatbot.system_prompt,
        Chatbot.is_active,
    ]

    # Permissions
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True

    # Pagination
    page_size = 50
    page_size_options = [25, 50, 100, 200]
