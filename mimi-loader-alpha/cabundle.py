"""Поиск рабочего CA-бандла для TLS.

Бинарник, собранный на Fedora/RHEL, помнит путь /etc/pki/ca-trust/...,
которого на других дистрибутивах нет — requests тогда падает с
"Could not find a suitable TLS CA certificate bundle". Здесь ищем файл,
который реально существует, и подставляем его в окружение.
"""
import os
import ssl

CANDIDATES = (
    "/etc/ssl/certs/ca-certificates.crt",                 # Debian, Ubuntu, Arch, Alpine
    "/etc/pki/tls/certs/ca-bundle.crt",                   # Fedora, RHEL, Arch (симлинк)
    "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",  # Fedora, RHEL
    "/etc/ssl/ca-bundle.pem",                             # openSUSE
    "/etc/ssl/cert.pem",                                  # Alpine, BSD, macOS
    "/usr/share/ca-certificates/ca-bundle.crt",
)


def _ok(path):
    return bool(path) and os.path.isfile(path) and os.path.getsize(path) > 0


def find_ca_bundle():
    # 1. бандл, зашитый в сборку (certifi/cacert.pem), либо из pip-версии certifi
    try:
        import certifi
        if _ok(certifi.where()):
            return certifi.where()
    except Exception:
        pass
    # 2. системные пути
    cafile = ssl.get_default_verify_paths().cafile
    if _ok(cafile):
        return cafile
    for path in CANDIDATES:
        if _ok(path):
            return path
    return None


def setup_ca_bundle():
    """Задаёт REQUESTS_CA_BUNDLE и SSL_CERT_FILE, если текущие указывают в пустоту."""
    for var in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE"):
        value = os.environ.get(var)
        if value and not _ok(value):
            os.environ.pop(var)  # битое значение хуже, чем отсутствие

    if _ok(os.environ.get("REQUESTS_CA_BUNDLE")):
        return os.environ["REQUESTS_CA_BUNDLE"]

    path = find_ca_bundle()
    if path:
        os.environ["REQUESTS_CA_BUNDLE"] = path
        os.environ["SSL_CERT_FILE"] = path
    return path
