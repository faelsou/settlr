# Site público: landing (/) e login da área do cliente (/entrar). Só arquivos estáticos e nginx.
# A configuração é de runtime (ambiente), então a mesma imagem serve Minikube e produção.
FROM nginxinc/nginx-unprivileged:1.30-alpine

# A base atrasa correções do Alpine e do próprio nginx, e o Trivy do CI barra CVE crítica com
# correção publicada. A imagem trava o nginx na versão dela (/etc/apk/world); o `apk add` sem versão
# solta a trava e puxa o nginx mais novo do repositório do nginx.org, cuja chave já vem na imagem.
USER root
# hadolint ignore=DL3017,DL3018
RUN NGINX_REPO="https://nginx.org/packages/alpine/v$(cut -d. -f1,2 /etc/alpine-release)/main" \
 && apk upgrade --no-cache \
 && apk add --no-cache --upgrade --repository "$NGINX_REPO" \
      nginx nginx-module-geoip nginx-module-image-filter nginx-module-njs nginx-module-xslt
USER 101

# Valores padrão do ambiente local. Em produção o stack sobrescreve.
# SUPABASE_URL vazio = login local pelo /auth/dev-login da API.
# NGINX_ENTRYPOINT_LOCAL_RESOLVERS faz a imagem preencher NGINX_LOCAL_RESOLVERS com o DNS do container.
ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1 \
    APP_URL=http://127.0.0.1:3000 \
    API_UPSTREAM=http://webhook-api:8000 \
    WHATSAPP_NUMBER= \
    SUPABASE_URL= \
    SUPABASE_ANON_KEY=

COPY site/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY site/public /usr/share/nginx/html

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
