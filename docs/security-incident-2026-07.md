# 機密外洩事故 — 2026-07

## 發生什麼事

`.env`、`.env.local`、`.env.prod` 三個檔案從 v1.0.0 起就被 commit 進版控，而
`.gitignore` 完全沒有 env 相關規則。此 repo（`leon0719/fastapi_best_architecture`）
為**公開** repo，因此以下值長期公開可讀：

| 值 | 內容 | 影響 |
| --- | --- | --- |
| `ADMIN_SECRET_KEY` | `TyHxCkEA1Tet…Z9hC0ws` | SQLAdmin `SessionMiddleware` 的簽章金鑰。知道它即可**偽造已登入的 admin session**，不需要帳密 |
| `ADMIN_PASSWORD` | `admin123` | admin 面板密碼 |
| `ADMIN_USERNAME` | `admin` | admin 面板帳號 |
| `DB_PASSWORD` | `postgres` | PostgreSQL 密碼 |
| `REDIS_PASSWORD` | `redis_password` | Redis 密碼 |

同一把 `ADMIN_SECRET_KEY` 出現在三個檔案，代表 dev 與 prod 共用一把金鑰。

出現的 commit：`d7755bd25ba130f87640a6d77ef0d3e0358560e4`（v1.0.0）、
`68448f0eeba303f1b6632d50f26627085be23291`（v2.0.0），皆已推送到 `origin/master`。

### 併發發現的第二個問題

`app/common/core/admin.py` 的 `login()` 用 `==` 比對帳密，而
`admin_username` / `admin_password` 在 `Config` 的預設值是空字串。未設定這兩個
env 時，**送出空白的登入表單即可通過驗證**（`"" == ""`），等於無密碼進入後台。
這條路徑與金鑰外洩獨立存在。

## 已修正

- `.gitignore` 加入 `.env` / `.env.*`（保留 `*.example`），並用
  `git rm --cached` 將三個檔案移出版控（檔案保留在磁碟）。
- `.env.example` 移除 `admin123` 等可直接沿用的弱值，改為明確的 `CHANGEME-` 標記，
  並附上金鑰產生指令。
- 新增 `Config.security_issues()` / `Config.enforce_secure_settings()`：偵測
  placeholder 與開發預設值。`DEBUG=False` 時**直接 raise 拒絕啟動**，本機開發只印警告。
  在 `app/main.py` 建立 app 之前呼叫（`SessionMiddleware` 隨即要用這把金鑰）。
- `admin.py` 的 `login()`：帳密任一未設定即拒絕；改用 `secrets.compare_digest`
  常數時間比對；非 `str` 的表單值一律拒絕。
- 新增 `conftest.py` 建立測試環境變數基線 —— 原本測試會讀開發者本機的 `.env`，
  導致「有 .env 的人測試會過，剛 clone 的人一 import `app.main` 就炸」。
- 新增 `tests/test_security_settings.py` 釘住上述行為。
- 新增 gitleaks 掃描（`.gitleaks.toml` + pre-commit hook + CI `secrets` job）。
  注意：**gitleaks 的預設規則抓不到這次外洩的 `ADMIN_SECRET_KEY`** —— 43 字元的
  隨機字串不符合任何 provider token 樣式。真正攔得住的是自訂的
  `dotenv-file-committed` 規則（比對檔名，`.env` 進版控就擋，不看內容）。
- 本機 `.env` / `.env.local` 的 `ADMIN_SECRET_KEY` 已各自輪替為新的獨立金鑰；
  `.env.prod` 改為 `CHANGEME`，強制部署時填入實際值。

## 尚待處理

### 1. 輪替所有已部署環境的機密 —— 最高優先

修改模板不會使已外洩的值失效。**任何由此模板衍生、且沿用預設值的專案都應視為已受影響**：

- `ADMIN_SECRET_KEY`：重新產生。輪替後既有 admin session 全部失效（預期行為）。
- `ADMIN_PASSWORD`：改為強密碼。
- PostgreSQL / Redis 密碼：若曾使用 `postgres` / `redis_password` 上線，一併更換。
- 檢查 admin 面板的存取紀錄有無異常登入。

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. 清除 git 歷史

移出版控只讓機密不再出現在**最新** commit，上述兩個 commit 仍可讀取。
考量到 repo 公開且已被索引，應假設這些值已永久外流 —— **輪替（第 1 點）比清歷史重要**。

若仍要清除（會改寫已推送的歷史、需要 force push、所有協作者必須重新 clone）：

```bash
uvx --from git-filter-repo git-filter-repo \
  --path .env --path .env.local --path .env.prod --invert-paths

git remote add origin git@github.com:leon0719/fastapi_best_architecture.git
git push --force --all
```

執行前請先備份整個 repo。清除完成後，記得把 `.gitleaks.toml` 裡
`[allowlist] commits = [...]` 的那兩個 SHA 一併刪除。

### 3. 考慮將 repo 轉為 private

此模板含公司內部開發慣例，公開的效益有限，卻讓任何設定疏失直接對外可見。
