"""The Caddyfile is the box's front door; these are the rules it must keep."""
import pathlib
import re

CADDYFILE = (pathlib.Path(__file__).resolve().parents[1] / "Caddyfile").read_text()
GLOBAL = CADDYFILE.split("}", 1)[0]


def test_plain_http_is_left_alone_for_the_certificate_download():
    # A laptop that does not trust the box CA yet opens http://<box>/ to get it.
    # Caddy's automatic HTTP->HTTPS redirect would send that to https://<box>:3001,
    # which is precisely the certificate the laptop cannot verify.
    assert "auto_https disable_redirects" in GLOBAL


def test_every_product_port_is_served():
    for port in (3080, 3001, 3002, 7860, 4000):
        assert re.search(rf"^\{{\$BOX_HOST\}}:{port}, ", CADDYFILE, re.M), port
    assert ":80 {" in CADDYFILE


def test_the_certificate_is_downloadable_by_its_public_name():
    assert "handle /nufi-box-ca.crt {" in CADDYFILE
    assert "rewrite * /root.crt" in CADDYFILE
