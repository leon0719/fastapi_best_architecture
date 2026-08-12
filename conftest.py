"""測試環境的環境變數基線。

必須在任何 app 模組被 import 之前設定:`app.common.core.config` 在 import 時就
建立 `config = Config()` 單例,而 `app.main` 會拿它跑 enforce_secure_settings()。

沒有這層基線的話,測試會去讀開發者本機的 .env —— 有 .env 的人測試會過,剛 clone
下來的人(或 CI)因為 DEBUG 預設 False 且全是預設值,一 import app.main 就 raise。
測試結果不該取決於某台機器上有沒有那個檔案。
"""

import os

_TEST_ENV = {
    "DEBUG": "true",
    "ADMIN_SECRET_KEY": "test-only-secret-key-not-used-anywhere-real-0123456789",
    "ADMIN_USERNAME": "test-admin",
    "ADMIN_PASSWORD": "test-only-password",
    "DB_PASSWORD": "test-only-db-password",
    "REDIS_PASSWORD": "test-only-redis-password",
}

# setdefault:真實環境變數優先,才不會蓋掉使用者刻意指定的測試設定。
for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)
