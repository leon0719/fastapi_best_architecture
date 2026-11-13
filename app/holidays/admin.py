"""Admin view for Holiday(颱風假、公司休假等臨時異動在這裡手動加)。"""

from app.audit.admin import AdminAuditMixin
from app.holidays.models import Holiday


class HolidayAdmin(AdminAuditMixin, model=Holiday):
    """行事曆例外日:平日放假或週末補班。"""

    name = "Holiday"
    name_plural = "Holidays"
    icon = "fa-solid fa-calendar-day"

    column_list = [Holiday.day, Holiday.name, Holiday.is_holiday]
    column_searchable_list = [Holiday.name]
    column_sortable_list = [Holiday.day]
    column_default_sort = [(Holiday.day, True)]
    form_columns = [Holiday.day, Holiday.name, Holiday.is_holiday]
    page_size = 50
