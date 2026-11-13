# 每日異地備份 sidecar:pg_dump 版本跟 db 映像一致(postgres:16-alpine),再加 aws-cli 上傳 S3
FROM postgres:16-alpine
RUN apk add --no-cache aws-cli
COPY backup.sh /backup.sh
ENTRYPOINT ["/bin/sh", "/backup.sh"]
