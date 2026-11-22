# Site público: landing e login

O serviço `site` serve a landing em `/` e o login da área do cliente em `/entrar`. É um nginx sem root com arquivos estáticos. Não fala com o banco e não guarda sessão.

| Arquivo | O que é |
| --- | --- |
| [`site/public/index.html`](../site/public/index.html) e [`assets/landing.js`](../site/public/assets/landing.js) | Landing em português, inglês e espanhol |
| [`site/public/entrar/index.html`](../site/public/entrar/index.html) e [`assets/login.js`](../site/public/assets/login.js) | Login, recuperação de senha e contato pelo WhatsApp |
| [`site/nginx/default.conf.template`](../site/nginx/default.conf.template) | Rotas, CSP, cache, `/config.js` e o proxy do login local |
| [`docker/site.Dockerfile`](../docker/site.Dockerfile) | Imagem `cobranca-site` |
| [`k8s/minikube/site/`](../k8s/minikube/site/) | ConfigMap, Deployment e Service do Minikube |
| `site` em [`docker/stack.yml`](../docker/stack.yml) | Produção no Swarm, em `DOMAIN` e `www.DOMAIN` |

## Mesmo visual no painel

O painel (`web/`) usa a identidade do site: Geist e Geist Mono, Sora só na marca, violeta `#5b3df5`/`#7c5cff`, lima `#c6f432` e a mesma marca. O `/login`, o `/comecar` e o `/convite/[token]` do painel repetem o `/entrar`: fundo escuro, aurora e a fila de exemplo. Os componentes ficam em [`web/components/auth.tsx`](../web/components/auth.tsx) e as classes `auth-*` em [`web/app/globals.css`](../web/app/globals.css). Mudou o `/entrar`? Mude os dois. As telas de operação seguem claras, por legibilidade de tabela.

## Idiomas do painel

O painel fala português (Brasil), inglês (EUA) e espanhol, como o site. Cada texto fica em [`web/lib/messages.ts`](../web/lib/messages.ts) como `[pt-BR, en-US, es]`: o build quebra se faltar uma tradução ou se a chave não existir. Em componente, `const { t } = useI18n()` e `t("chave", { variavel })`; fora de componente, `tr()`.

- A escolha fica em `settlr-lang`, a mesma chave do site, e chega do `/entrar` pelo `&lang=` da entrega da sessão. Sem escolha, vale o idioma do navegador.
- O seletor fica na entrada (login, comecar, convite) e no rodapé do menu lateral.
- Datas e números seguem o idioma. A moeda é sempre o real (`R$`).
- Continua em português o que vai para o devedor (templates da régua, mensagem padrão de aprovação, respostas do agente) e o que vem pronto da API (mensagens de erro e o motivo das exceções).

## Configuração

Tudo é de runtime. A mesma imagem serve o Minikube e a produção. O nginx monta o `/config.js` com estas variáveis, e as páginas leem dele.

| Variável | Padrão | Efeito |
| --- | --- | --- |
| `APP_URL` | `http://127.0.0.1:3000` | Painel que recebe a sessão depois do login. Em produção, `https://app.DOMAIN` |
| `API_UPSTREAM` | `http://webhook-api:8000` | Gateway do login local. No Kubernetes, nome completo do Service |
| `WHATSAPP_NUMBER` | vazio | WhatsApp comercial, só dígitos, com 55 e DDD. Vazio: os botões levam ao bloco do piloto |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | vazios | Preenchidos: login por e-mail e senha no Supabase Auth. Vazios: login local |

A anon key do Supabase é pública por desenho, e nada no `/config.js` é segredo. Os valores entram numa string JavaScript: não use aspas neles.

## Como o login chega ao painel

O painel mora em outra origem (`app.DOMAIN`), e o `localStorage` de uma origem não é lido pela outra. O site autentica e entrega a sessão pelo fragmento da URL, como os links de e-mail do Supabase:

```text
/entrar ──(Supabase signInWithPassword)──▶ sessão
        ──▶ APP_URL/login#access_token=…&refresh_token=…&lang=…
painel /login lê o fragmento, apaga da barra, grava a sessão e vai para /inicio
```

- O fragmento (`#…`) não vai para nenhum servidor nem para o log do Traefik.
- O `lang` leva o idioma escolhido no site (`pt-BR`, `en-US` ou `es`). O painel grava em `settlr-lang` e abre nesse idioma.
- O painel apaga o fragmento com `history.replaceState` antes de qualquer outra coisa. Com o refresh token, o Supabase renova a sessão no painel.
- No modo local (sem Supabase), o form pede e-mail e apelido da empresa e chama `POST /auth/dev-login` na mesma origem. O nginx repassa só essa rota ao gateway. Em produção a API recusa o dev-login.
- "Esqueci a senha" chama `resetPasswordForEmail` com retorno para `APP_URL/login`. A resposta na tela é a mesma exista ou não a conta.

No Supabase, `APP_URL/login` precisa estar em **Authentication → URL Configuration → Redirect URLs**.

## Minikube

A imagem só existe no Docker Hub depois do primeiro push do CI. Até lá, build local e carga nos nós:

```bash
docker build -f docker/site.Dockerfile -t faelsouz/cobranca-site:dev .
docker save faelsouz/cobranca-site:dev -o /tmp/site.tar
minikube -p devops-dev image load /tmp/site.tar      # carrega em todos os nós
kubectl apply -k k8s/minikube
kubectl -n cobranca port-forward svc/site 8080:8080
```

Landing em http://127.0.0.1:8080 e login em http://127.0.0.1:8080/entrar (e-mail `operador@demo.local`, empresa `demo`). O login entrega a sessão ao painel em http://127.0.0.1:3000, então o port-forward do `frontend-web` também precisa estar aberto.

`minikube image load` direto da tag pode falhar com `blob … not found`. O caminho pelo `.tar` contorna.

Depois do CI, `scripts/deploy-minikube.sh <tag>` troca a imagem do site junto com a da API e do painel, e o smoke test confere `/healthz` e `/entrar/`.

## Segurança

- CSP sem script inline: só `self`, o `supabase-js@2.45.4` do jsDelivr, Google Fonts e o `SUPABASE_URL` no `connect-src`. `frame-ancestors 'none'`.
- No Kubernetes: usuário 101, raiz só leitura, sem capabilities, `seccompProfile: RuntimeDefault`. O nginx escreve só em três `emptyDir`.
- O site não recebe senha no modo de produção: o browser fala direto com o Supabase.

## Limites conhecidos

- O painel ainda não tem tela de nova senha. O link de recuperação do Supabase entra no painel com a sessão, mas não pede a senha nova.
- O protótipo do `/comecar` não está no site. Conta nova abre pela conversa no WhatsApp.
