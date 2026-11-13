# 稽核軌跡

實作在 `app/audit/`。一張 `audit_logs` 表收兩種來源:

| 來源 | 怎麼寫 | 交易 |
|---|---|---|
| SQLAdmin 後台 | `class XxxAdmin(AdminAuditMixin, model=Xxx)` 自動記新增/修改/刪除(欄位 diff、IP) | sqladmin 先 commit,軌跡另一筆交易(寫入失敗會在後台顯示錯誤) |
| 業務層 | service 在 commit 前呼叫 `record_audit(...)` | 與被改的資料同一交易 |

```python
before = snapshot(order)
order.status = "cancelled"
record_audit(
    self.db,
    action="cancel",
    target_type="Order",
    target_id=order.id,
    target_label=str(order),
    before=before,
    after=snapshot(order),
    actor=f"user:{user.id}",
    ip=client_ip(request),
)
self.db.commit()
```

- 欄位名含 password / secret / token / digest / challenge / api_key / bank_account 的值會遮成「（已變更）」;
  其他機密欄位用 `masked=frozenset({...})`(後台用類別屬性 `audit_masked_fields`)。
- 後台是共用帳密,actor 記 `admin`,辨識靠時間與 IP(`X-Real-IP`)。
- 保留期:`AUDIT_RETENTION_DAYS`(預設 365,0 = 永久),每日排程刪除。
- 範例:`UserService` 的 create/update/delete、`UserAdmin`、`ChatbotAdmin`、`HolidayAdmin`。
