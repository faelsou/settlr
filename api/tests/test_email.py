"""O HTML transacional leva a imagem no mesmo MIME, pelo cid."""

from app.channels.email import build_message


def test_imagem_inline_viaja_com_o_html():
    png = b"\x89PNG\r\n\x1a\n"
    msg = build_message(
        "de@kitou.test",
        "para@kitou.test",
        "Assunto",
        "texto",
        '<img src="cid:kitou-logo" alt="Kitou">',
        [("kitou-logo", png, "png")],
    )
    imagens = [parte for parte in msg.walk() if parte.get_content_type() == "image/png"]
    assert len(imagens) == 1
    assert imagens[0]["Content-ID"] == "<kitou-logo>"
    assert imagens[0].get_content() == png
    html = msg.get_body(preferencelist=("html",))
    assert html is not None
    assert 'src="cid:kitou-logo"' in html.get_content()
