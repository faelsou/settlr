"""Guia de uso do painel. Sai quando a empresa entra no banco, para o e-mail do dono."""

from html import escape

from app.channels.email import send_email
from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_INK = "#12101f"
_MUTED = "#5f5a78"
_BRAND = "#5b3df5"
_LIME = "#c6f432"
_PAPER = "#f7f6fc"
_LINE = "#e3def7"


def welcome_copy(company: str, panel_url: str) -> tuple[str, str, str]:
    """Assunto, texto puro e HTML do mesmo passo a passo."""
    name = " ".join(company.split()) or "sua empresa"
    panel = panel_url.rstrip("/")
    login = f"{panel}/login"
    settings = f"{panel}/configuracoes"
    titles = f"{panel}/titulos"
    home = f"{panel}/inicio"
    subject = f"Como usar o painel — {name}"
    text = _text(name, login, settings, titles, home)
    html = _html(name, login, settings, titles, home)
    return subject, text, html


def deliver_welcome(company: str, to: str, panel_url: str | None = None) -> bool:
    """True quando o SMTP aceitou. Falha de envio não desfaz o cadastro."""
    destination = (to or "").strip()
    if not destination:
        return False
    panel = (panel_url or get_settings().panel_base_url).rstrip("/")
    subject, text, html = welcome_copy(company, panel)
    try:
        send_email(destination, subject, text, html)
    except Exception as exc:
        log.warning("boas_vindas.nao_enviado", to=destination, motivo=str(exc))
        return False
    return True


def _text(name: str, login: str, settings: str, titles: str, home: str) -> str:
    return (
        f"A conta {name} entrou no Settlr.\n\n"
        "A cobrança ainda não dispara. A conta nasce desligada para você conferir a carteira "
        "antes de qualquer mensagem.\n\n"
        f"1. Entre no painel\n{login}\n"
        "Use o e-mail desta mensagem. Cada pessoa entra pelo próprio acesso. "
        "Não há senha para repassar.\n\n"
        "2. Complete o disparo e ligue a conta\n"
        f"{settings}\n"
        "Em Disparo, cadastre o WhatsApp da empresa. O primeiro número envia; dá para ter até cinco. "
        "Em Conta, registre a base legal. Horário, régua e política já nascem com um padrão. "
        "Ative a conta na mesma tela. Se faltar algo, a ativação diz o que completar.\n\n"
        "3. Importe os títulos em aberto\n"
        f"{titles}\n"
        "Use Importar CSV. Uma linha é uma cobrança. Cabeçalho:\n"
        "referencia,nome,documento,telefone,email,valor,vencimento,descricao,"
        "txid,linha_digitavel,pix_copia_cola,link\n"
        "Arquivo em UTF-8. Se uma linha estiver errada, nada é gravado.\n\n"
        "4. Confira antes de cobrar\n"
        "Na lista, olhe nome, documento, valor, vencimento e o status Aberto. "
        "Título sem PIX ou boleto fica em Sem PIX ou boleto e não entra na régua até o código chegar.\n\n"
        "5. A régua trabalha sozinha\n"
        "Com a conta ativa, o aviso sai 3 dias antes, no dia do vencimento e depois dele, "
        "até o 30º dia, quando o título vai para a fila humana. "
        "Fora do horário (padrão, 8h às 20h, de segunda a sábado) a mensagem espera. "
        "A mesma etapa não repete. Quem pede para parar deixa de ser cobrado.\n\n"
        "6. Opere o que pede gente\n"
        f"{home}\n"
        "Início mostra as filas. Exceções e Pagamentos são o dinheiro que entrou. "
        "Conversas é o WhatsApp que a equipe assume. Entregas mostra o que não chegou. "
        "Aprovações guarda pedido fora da política. Métricas compara a recuperação com o atraso de antes.\n\n"
        "7. Chame a equipe\n"
        f"{settings}\n"
        "Na seção Equipe, convide o financeiro e o atendente. "
        "O financeiro confirma a baixa. O atendente acompanha a fila e não confirma baixa. "
        "O dono configura a política. O convite chega por e-mail, com um link só da pessoa.\n"
    )


def _html(name: str, login: str, settings: str, titles: str, home: str) -> str:
    safe = escape(name)
    steps = [
        (
            "01",
            "Entre no painel",
            "Use o e-mail desta mensagem. Cada pessoa entra pelo próprio acesso. "
            "Não há senha para repassar.",
            login,
            "Abrir o login",
        ),
        (
            "02",
            "Complete o disparo e ligue a conta",
            "Em Disparo, cadastre o WhatsApp da empresa. O primeiro número envia; dá para ter até cinco. "
            "Em Conta, registre a base legal. Horário, régua e política já nascem com um padrão. "
            "Ative a conta na mesma tela. Se faltar algo, a ativação diz o que completar.",
            settings,
            "Abrir Configurações",
        ),
        (
            "03",
            "Importe os títulos em aberto",
            "Em Títulos, use Importar CSV. Uma linha é uma cobrança. O arquivo precisa estar em UTF-8. "
            "Se uma linha estiver errada, nada é gravado.",
            titles,
            "Abrir Títulos",
        ),
        (
            "04",
            "Confira antes de cobrar",
            "Na lista, olhe nome, documento, valor, vencimento e o status Aberto. "
            "Título sem PIX ou boleto fica na lista Sem PIX ou boleto e não entra na régua até o código chegar.",
            titles,
            "Conferir a carteira",
        ),
        (
            "05",
            "Deixe a régua trabalhar",
            "Com a conta ativa, o aviso sai 3 dias antes, no dia do vencimento e depois dele, "
            "até o 30º dia, quando o título vai para a fila humana. "
            "Fora do horário (padrão, 8h às 20h, de segunda a sábado) a mensagem espera. "
            "A mesma etapa não repete. Quem pede para parar deixa de ser cobrado.",
            home,
            "Ver o Início",
        ),
        (
            "06",
            "Opere o que pede gente",
            "Início mostra as filas. Exceções e Pagamentos são o dinheiro que entrou. "
            "Conversas é o WhatsApp que a equipe assume. Entregas mostra o que não chegou. "
            "Aprovações guarda pedido fora da política. Métricas compara a recuperação com o atraso de antes.",
            home,
            "Abrir as filas",
        ),
        (
            "07",
            "Chame a equipe",
            "Em Configurações, seção Equipe, convide o financeiro e o atendente. "
            "O financeiro confirma a baixa. O atendente acompanha a fila e não confirma baixa. "
            "O dono configura a política. O convite chega por e-mail, com um link só da pessoa.",
            settings,
            "Convidar a equipe",
        ),
    ]
    rows = "\n".join(_step_row(*step) for step in steps)
    header = (
        "referencia, nome, documento, telefone, email, valor, vencimento, descricao, "
        "txid, linha_digitavel, pix_copia_cola, link"
    )
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Como usar o painel — {safe}</title>
</head>
<body style="margin:0;padding:0;background:{_PAPER};">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;">
    A conta {safe} está no Settlr. A cobrança só começa depois que você conferir a carteira e ligar a conta.
  </div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_PAPER};">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;">
          <tr>
            <td style="background:{_INK};border-radius:28px 28px 0 0;padding:32px 36px 28px;">
              <p style="margin:0;font-family:Georgia,'Times New Roman',serif;font-size:28px;line-height:1;color:#ffffff;">
                Settlr<span style="color:{_LIME};">.</span>
              </p>
              <p style="margin:22px 0 0;font-family:Georgia,'Times New Roman',serif;font-size:36px;line-height:1.15;color:#ffffff;">
                Cobrou, recebeu, conciliou.
              </p>
              <p style="margin:14px 0 0;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.5;color:#d9d6ea;">
                A conta {safe} entrou no painel. Estes são os passos até a primeira cobrança sair sozinha.
              </p>
            </td>
          </tr>
          <tr>
            <td style="background:#ffffff;padding:8px 36px 8px;border-left:1px solid {_LINE};border-right:1px solid {_LINE};">
              <p style="margin:24px 0 8px;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.6;color:{_INK};">
                A cobrança ainda não dispara. A conta nasce desligada de propósito: dá tempo de importar a base e conferir antes de qualquer mensagem.
              </p>
            </td>
          </tr>
          {rows}
          <tr>
            <td style="background:#ffffff;padding:8px 36px 28px;border-left:1px solid {_LINE};border-right:1px solid {_LINE};">
              <p style="margin:8px 0 10px;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:12px;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;color:{_BRAND};">
                Cabeçalho do CSV
              </p>
              <p style="margin:0;padding:14px 16px;background:{_PAPER};border-radius:14px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;line-height:1.55;color:{_INK};">
                {escape(header)}
              </p>
            </td>
          </tr>
          <tr>
            <td align="center" style="background:#ffffff;padding:4px 36px 36px;border-left:1px solid {_LINE};border-right:1px solid {_LINE};border-bottom:1px solid {_LINE};border-radius:0 0 28px 28px;">
              <a href="{escape(login, quote=True)}" style="display:inline-block;background:{_BRAND};color:#ffffff;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:15px;font-weight:700;text-decoration:none;padding:14px 28px;border-radius:999px;">
                Abrir o painel
              </a>
            </td>
          </tr>
          <tr>
            <td style="padding:18px 8px 0;">
              <p style="margin:0;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:12px;line-height:1.5;color:{_MUTED};">
                Settlr enviou este guia porque a conta {safe} foi cadastrada. O financeiro confirma a baixa. O atendente acompanha a fila. O dono configura a política.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _step_row(number: str, title: str, body: str, href: str, label: str) -> str:
    return f"""<tr>
            <td style="background:#ffffff;padding:14px 36px 6px;border-left:1px solid {_LINE};border-right:1px solid {_LINE};">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td width="52" valign="top" style="width:52px;">
                    <p style="margin:0;width:40px;height:40px;background:{_INK};border-radius:14px;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:13px;font-weight:700;line-height:40px;text-align:center;color:{_LIME};">
                      {number}
                    </p>
                  </td>
                  <td valign="top" style="padding-bottom:8px;">
                    <p style="margin:0;font-family:Georgia,'Times New Roman',serif;font-size:20px;line-height:1.3;color:{_INK};">{escape(title)}</p>
                    <p style="margin:6px 0 0;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:14px;line-height:1.6;color:{_MUTED};">{escape(body)}</p>
                    <p style="margin:8px 0 0;">
                      <a href="{escape(href, quote=True)}" style="font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:13px;font-weight:700;color:{_BRAND};text-decoration:none;">{escape(label)}</a>
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""
