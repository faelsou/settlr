#!/bin/sh
# Copia o webhook real quando o Secret critical-page existe.
# Sem o arquivo, o receiver critical fica com um URL que não entrega
# e o receiver aiops continua.
set -eu
mkdir -p /tmp/alertmanager
if [ -s /etc/alertmanager/critical-secret/SLACK_CRITICAL_WEBHOOK ]; then
  cp /etc/alertmanager/critical-secret/SLACK_CRITICAL_WEBHOOK /tmp/alertmanager/SLACK_CRITICAL_WEBHOOK
else
  cp /etc/alertmanager/critical-default/SLACK_CRITICAL_WEBHOOK /tmp/alertmanager/SLACK_CRITICAL_WEBHOOK
fi
exec /bin/alertmanager \
  --config.file=/etc/alertmanager/alertmanager.yml \
  --storage.path=/alertmanager \
  --web.external-url=http://127.0.0.1:9093
