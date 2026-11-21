# Site público: landing (/) e login da área do cliente (/entrar). Só arquivos estáticos e nginx.
# A configuração é de runtime (ambiente), então a mesma imagem serve Minikube e produção.
FROM nginxinc/nginx-unprivileged:1.27-alpine

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
