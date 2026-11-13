"""後台稽核:寫入軌跡的 AdminAuditMixin,以及查軌跡的唯讀 view。

任何 ModelView 繼承 AdminAuditMixin 就會記錄後台的新增、修改、刪除:

    class ProductAdmin(AdminAuditMixin, ModelView, model=Product):
        audit_masked_fields = frozenset({"license_key"})  # 額外要遮罩的欄位(password/token 等已預設遮罩)
"""

from typing import Any, ClassVar, cast
from zoneinfo import ZoneInfo

from markupsafe import Markup
from sqladmin import ModelView
from sqladmin.filters import AllUniqueStringValuesFilter, StaticValuesFilter
from sqladmin.helpers import get_object_identifier
from sqlalchemy.orm import Session, sessionmaker
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from app.audit.models import AuditLog, AuditSource
from app.audit.services import record_audit, snapshot
from app.common.core.request_context import client_ip

ADMIN_ACTOR = "admin"  # 後台是單一共用帳密,分不出是哪個人;能留的是時間、IP、改了什麼


class AdminAuditMixin(ModelView):
    """後台對這個 model 的新增、修改、刪除都留一筆 AuditLog。

    掛在 sqladmin 的 insert_model / update_model / delete_model,而不是 on_model_change 這些 hook:
    整個流程(hook、commit)都在 super() 裡跑完才回來,view 自己的檢查擋下操作時這裡根本走不到寫入;
    且子類覆寫 hook 忘了呼叫 super() 也不會默默漏記。舊值在呼叫 super() 之前先查,軌跡在 super()
    回來(變更已 commit)之後才寫。

    取捨:sqladmin 先 commit 變更才輪到這裡,軌跡寫入失敗時變更已生效、無法一起回滾;例外照常往外拋,
    後台會顯示錯誤、server log 留 stack trace,好過默默漏記。業務層要同交易請用 record_audit()。
    """

    audit_masked_fields: ClassVar[frozenset[str]] = frozenset()

    async def insert_model(self, request: Request, data: dict) -> Any:
        obj = await super().insert_model(request, data)
        await run_in_threadpool(self._write, "create", str(get_object_identifier(obj)), {}, obj, client_ip(request))
        return obj

    async def update_model(self, request: Request, pk: str, data: dict) -> Any:
        before, _ = await run_in_threadpool(self._snapshot_by_pk, pk)
        obj = await super().update_model(request, pk, data)
        await run_in_threadpool(self._write, "update", pk, before, obj, client_ip(request))
        return obj

    async def delete_model(self, request: Request, pk: Any) -> None:
        before, label = await run_in_threadpool(self._snapshot_by_pk, str(pk))
        await super().delete_model(request, pk)
        await run_in_threadpool(self._write, "delete", str(pk), before, None, client_ip(request), label)

    def _session(self) -> Session:
        return cast("sessionmaker[Session]", self.session_maker)()

    def _write(self, action: str, pk: str, before: dict, obj: Any, ip: str | None, label: str | None = None) -> None:
        with self._session() as session:
            after: dict[str, Any] = {}
            if obj is not None:
                current = session.execute(self._stmt_by_identifier(pk)).scalars().first()
                if current is not None:
                    after, label = snapshot(current), str(current)
            if action == "update" and before == after:  # 沒改任何欄位的「存檔」不留紀錄
                return
            record_audit(
                session,
                action=action,
                target_type=self.model.__name__,
                target_id=pk,
                target_label=label,
                before=before,
                after=after,
                actor=ADMIN_ACTOR,
                source=AuditSource.ADMIN,
                ip=ip,
                masked=self.audit_masked_fields,
            )
            session.commit()

    def _snapshot_by_pk(self, pk: str) -> tuple[dict[str, Any], str | None]:
        """(欄位快照, 名稱);名稱在 session 還開著時取,__str__ 可能要讀關聯。"""
        with self._session() as session:
            obj = session.execute(self._stmt_by_identifier(pk)).scalars().first()
            return ({}, None) if obj is None else (snapshot(obj), str(obj))


_TAIPEI = ZoneInfo("Asia/Taipei")
_ACTIONS = {"create": "新增", "update": "修改", "delete": "刪除"}


def _value(value: Any) -> str:
    if value is None or value == "":
        return "（空）"
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def _changes_text(model: AuditLog, _attribute: str) -> Markup:
    """一個欄位一行:修改是「欄位:舊 → 新」,新增只列新值、刪除只列舊值。"""
    lines = []
    for field, (old, new) in (model.changes or {}).items():
        if model.action == "create":
            text = _value(new)
        elif model.action == "delete":
            text = _value(old)
        else:
            text = f"{_value(old)} → {_value(new)}"
        lines.append(Markup("<b>{}</b>：{}").format(field, text))  # format 會跳脫值,擋 XSS
    return Markup("<br>").join(lines)


def _target_text(model: AuditLog, _attribute: str) -> str:
    return f"{model.target_label}（#{model.target_id}）" if model.target_label else f"#{model.target_id}"


def _time_text(model: AuditLog, _attribute: str) -> str:
    return model.created_at.astimezone(_TAIPEI).strftime("%Y-%m-%d %H:%M:%S")


class AuditLogAdmin(ModelView, model=AuditLog):
    """稽核軌跡,只能看。"""

    name = "Audit Log"
    name_plural = "Audit Logs"
    icon = "fa-solid fa-clock-rotate-left"

    column_list = [
        AuditLog.created_at,
        AuditLog.source,
        AuditLog.actor,
        AuditLog.action,
        AuditLog.target_type,
        AuditLog.target_id,
        AuditLog.ip,
        AuditLog.changes,
    ]
    column_details_list = [*column_list, AuditLog.request_id]
    column_default_sort = [(AuditLog.created_at, True), (AuditLog.id, True)]
    # sqladmin 0.32 的 column_filters 要放 filter 物件,直接放欄位會在列表頁出錯
    column_filters = [
        AllUniqueStringValuesFilter(AuditLog.target_type, title="資料種類"),
        StaticValuesFilter(AuditLog.action, list(_ACTIONS.items()), title="動作"),
        StaticValuesFilter(AuditLog.source, [(s.value, s.value) for s in AuditSource], title="來源"),
    ]
    column_searchable_list = [AuditLog.target_id, AuditLog.target_label, AuditLog.actor, AuditLog.request_id]
    column_formatters = {
        AuditLog.created_at: _time_text,
        AuditLog.target_id: _target_text,
        AuditLog.changes: _changes_text,
    }
    column_formatters_detail = column_formatters

    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True
