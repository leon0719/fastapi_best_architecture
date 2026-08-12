"""get_db 應集中定義於 common/db,而非各 app 重複定義。"""

import inspect

import pytest

pytestmark = pytest.mark.unit


def test_get_db_lives_in_common():
    from app.common.db.database import get_db

    assert inspect.isgeneratorfunction(get_db)


def test_views_reuse_common_get_db():
    from app.chatbots import views as chatbot_views
    from app.common.db.database import get_db
    from app.users import views as user_views

    assert user_views.get_db is get_db
    assert chatbot_views.get_db is get_db
