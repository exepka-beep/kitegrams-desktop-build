"""Вшить публичный RSA-ключ сервера KiteGrams в десктопный клиент.

Зачем
-----
Сервер создаёт ключевую пару при первом старте (`data/server_rsa.pem`), заранее
её знать нельзя. Клиент проверяет по этому ключу подпись в обмене ключами
MTProto, поэтому ключ в него попадает на сборке:

    GET http://<сервер>/owpengram/server-info
    {"rsa_public_key_pem": "...", "dc_id": 2, ...}

В tdesktop ключи лежат в `Telegram/SourceFiles/mtproto/mtproto_dc_options.cpp`:

    const char *kPublicRSAKeys[] = { "\\
    -----BEGIN RSA PUBLIC KEY-----\\n\\
    MIIBCgKCAQEA...\\n\\
    -----END RSA PUBLIC KEY-----" };

Это compile-time константа, рантаймом не переопределяется — в отличие от
`dc_options`, которые сервер присылает в `help.getConfig`. Поэтому в CI её надо
подменить перед сборкой, иначе рукопожатие провалится и клиент повиснет на
«Connecting…».

Тестовый массив `kTestPublicRSAKeys` не трогаем: он выбирается только при
`Environment::Test`, а такой сборки у нас нет.

Использование
-------------
    set_server_key.py --source <mtproto_dc_options.cpp> --pem <server-rsa-public.pem>
    set_server_key.py --source <...> --pem <...> --check

Код возврата ненулевой на любой ошибке: собрать клиент с чужим ключом хуже,
чем не собрать вовсе.
"""

import argparse
import os
import re
import sys

# stdout раннера Windows — cp1252, а печатаем мы по-русски: без этого шаг
# падает на `UnicodeEncodeError: 'charmap' codec ...`. См. bake_server_key.py.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

BEGIN = "-----BEGIN RSA PUBLIC KEY-----"
END = "-----END RSA PUBLIC KEY-----"

# Блок в C++:
#
#     const char *kPublicRSAKeys[] = { "\
#     -----BEGIN RSA PUBLIC KEY-----\n\
#     MIIBCgKCAQEA...\n\
#     -----END RSA PUBLIC KEY-----" };
BLOCK = re.compile(
    r'const char \*kPublicRSAKeys\[\] = \{ "\\\n'
    r"-----BEGIN [A-Z0-9 ]*PUBLIC KEY-----\\n\\\n"
    r"(?:[A-Za-z0-9+/=]+\\n\\\n)+"
    r'-----END [A-Z0-9 ]*PUBLIC KEY-----" \};'
)


def read_normalized(path):
    """Текст файла с нормализованными переводами строк + признак «был CRLF»."""
    with open(path, "rb") as handle:
        raw = handle.read()
    text = raw.decode("utf-8", errors="surrogateescape").replace("\r\n", "\n")
    return text, b"\r\n" in raw


def write_text(path, text, crlf):
    out = text.replace("\n", "\r\n") if crlf else text
    with open(path, "wb") as handle:
        handle.write(out.encode("utf-8", errors="surrogateescape"))


def read_pem(path):
    with open(path, "rb") as handle:
        raw = handle.read().decode("utf-8", errors="replace")
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines or lines[0] != BEGIN or lines[-1] != END:
        raise ValueError(
            "не похоже на PEM публичного ключа: первая строка %r, последняя %r"
            % (lines[0] if lines else None, lines[-1] if lines else None)
        )
    body = "".join(lines[1:-1])
    if not body:
        raise ValueError("пустое тело ключа")
    return lines, body


def cpp_block(pem_lines):
    out = ['const char *kPublicRSAKeys[] = { "\\']
    for line in pem_lines[:-1]:
        out.append("%s\\n\\" % line)
    out.append('%s" };' % pem_lines[-1])
    return "\n".join(out)


def body_of(cpp_text):
    """Тело ключа из C++-блока — без `\\n\\` и переводов строк.

    Сравнивать `body in text` напрямую нельзя: в C++ ключ разбит на строки по
    64 символа, между ними `\\n\\`, поэтому слитая строка тела в файле
    подстрокой не встречается.
    """
    match = re.search(
        r"-----BEGIN [A-Z0-9 ]*PUBLIC KEY-----\\n\\\n(.*?)-----END",
        cpp_text, re.S,
    )
    if not match:
        return None
    return match.group(1).replace("\\n\\\n", "").replace("\n", "")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True,
                        help="путь к mtproto_dc_options.cpp")
    parser.add_argument("--pem", required=True, help="файл с публичным ключом")
    parser.add_argument("--check", action="store_true",
                        help="только проверить, что ключ уже вшит")
    args = parser.parse_args()

    if not os.path.isfile(args.source):
        print("FAIL: нет файла %s" % args.source)
        return 1
    try:
        pem_lines, body = read_pem(args.pem)
    except Exception as error:
        print("FAIL: %s: %s" % (type(error).__name__, error))
        return 1

    text, crlf = read_normalized(args.source)

    match = BLOCK.search(text)
    if not match:
        print("FAIL: в %s не нашёл блок kPublicRSAKeys" % args.source)
        return 1

    current = match.group(0)
    if body_of(current) == body:
        print("ключ уже вшит (тело %d символов, %s...)" % (len(body), body[:24]))
        return 0

    if args.check:
        print("FAIL: в файле другой ключ — сборка ушла бы с чужим")
        return 1

    text = text[:match.start()] + cpp_block(pem_lines) + text[match.end():]
    write_text(args.source, text, crlf)

    # Самопроверка: перечитываем файл и убеждаемся, что ключ на месте.
    check, _ = read_normalized(args.source)
    again = BLOCK.search(check)
    if not again:
        print("FAIL: после подстановки блок kPublicRSAKeys не читается")
        return 1
    if body_of(again.group(0)) != body:
        print("FAIL: тело ключа в файле не совпало с ожидаемым")
        return 1
    if again.group(0) != cpp_block(pem_lines):
        print("FAIL: блок в файле отличается от сгенерированного")
        return 1

    print("ключ вшит: тело %d символов, %s..." % (len(body), body[:24]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
