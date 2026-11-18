"""Собрать overlay KiteGrams для десктопного клиента на базе gramsrv-tdesktop.

Откуда берётся база
-------------------
`iamxvbaba/gramsrv-tdesktop` — форк официального `telegramdesktop/tdesktop`,
подогнанный под наш серверный стек (gramsrv/telesrv). Именно с ним сервер
рассчитан работать: в `gramsrv-main/internal/compat/tdesktop/` лежит отдельный
слой совместимости по проводу, а `cmd/telesrv-update` умеет отдавать обновления
по протоколу самого TDesktop (`/current4`).

Что делает скрипт
-----------------
1. Читает локальный клон базы (`--src`, по умолчанию `../../_tdesktop_src`),
   закреплённый на коммите из `BASE_REF`.
2. Применяет к нему список правок `PATCHES` — брендинг, адрес DC, ключ, отказ
   от официального автообновления.
3. Кладёт изменённые файлы в `files/` зеркально путям внутри репозитория.

В CI эти файлы просто копируются поверх свежего клона базы (шаг
`Apply the KiteGrams overlay`), ровно как в Android- и iOS-конвейерах.

Почему overlay целиком, а не `git apply`
----------------------------------------
Патч-файлы ломаются на любом сдвиге контекста, а overlay — это готовые файлы:
их нельзя «недоналожить». Цена — файлы лежат в репозитории целиком, зато
сборка либо видит ровно то, что мы проверили, либо падает на шаге проверки
брендинга, а не компилируется втихую с чужим адресом сервера.

Использование
-------------
    make_overlay.py --src ../../_tdesktop_src      # собрать overlay
    make_overlay.py --check                        # проверить готовый overlay

После сборки overlay нужно вшить ключ сервера:

    set_server_key.py --source files/Telegram/SourceFiles/mtproto/mtproto_dc_options.cpp \\
                      --pem ../../keys/server_rsa_public.pem

Почему ключ отдельно: он меняется при пересоздании идентичности сервера, и в
CI всё равно перепекается свежим из `/owpengram/server-info`. Держать его в
одном скрипте с брендингом — значит пересобирать брендинг из-за ключа.
"""

import argparse
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "files"))
DEFAULT_SRC = os.path.normpath(os.path.join(HERE, "..", "..", "_tdesktop_src"))

# Коммит базы, на который рассчитан overlay. Меняется вместе с `UPSTREAM_REF`
# в `.github/workflows/build-desktop.yml` — иначе якоря ниже разъедутся.
BASE_REF = "270f160c6e5289a33a75b4e1290103fc1cecdd60"

SERVER_HOST = "2.26.81.165"
SERVER_PORT = 2398
PUBLIC_BASE_URL = "http://kitegrams.duckdns.org"

# Правки. Каждый `old` обязан встречаться в файле РОВНО ОДИН РАЗ: скрипт падает
# и на нуле, и на двух совпадениях. Иначе правка либо не применится, либо
# применится не туда — и клиент соберётся с адресом официального Telegram.
PATCHES = [

    # --- 1. Брендинг: единственный источник имени приложения ------------------
    #
    # `core/version.h` — то место, откуда tdesktop берёт и заголовок окна, и имя
    # папки в %APPDATA% (`platform/win/specific_win.cpp:psAppDataPath()` собирает
    # путь как APPDATA + AppName). Одна правка даёт сразу и «KiteGrams Desktop» в
    # интерфейсе, и отдельный каталог данных, то есть отсутствие конфликта с
    # установленным официальным Telegram.
    (
        "Telegram/SourceFiles/core/version.h",
        'constexpr auto AppNameOld = "Telegram Win (Unofficial)"_cs;',
        'constexpr auto AppNameOld = "KiteGrams Win (Unofficial)"_cs;',
    ),
    (
        "Telegram/SourceFiles/core/version.h",
        'constexpr auto AppName = "Telegram Desktop"_cs;',
        'constexpr auto AppName = "KiteGrams Desktop"_cs;',
    ),
    # AppFile — имя ярлыка автозапуска в %APPDATA%\...\Startup. Официальный
    # Telegram кладёт туда Telegram.lnk; с общим именем два клиента затирали бы
    # друг другу автозапуск.
    (
        "Telegram/SourceFiles/core/version.h",
        'constexpr auto AppFile = "Telegram"_cs;',
        'constexpr auto AppFile = "KiteGrams"_cs;',
    ),

    # --- 2. ApplicationName: Qt-имя приложения --------------------------------
    #
    # Используется в путях Linux (XDG) и в single-instance-логике. Должно
    # отличаться от «TelegramDesktop», иначе две установки делят один профиль.
    (
        "Telegram/SourceFiles/core/launcher.cpp",
        '\tQApplication::setApplicationName(u"TelegramDesktop"_q);',
        '\tQApplication::setApplicationName(u"KiteGramsDesktop"_q);',
    ),

    # --- 3. Windows: AppUserModelID и ярлыки ----------------------------------
    #
    # AUMID — это то, по чему Windows группирует окна на панели задач, хранит
    # закрепления и адресует toast-уведомления. Совпади он с телеграмным —
    # Windows сочла бы оба клиента одним приложением: закреплённый ярлык вёл бы
    # в официальный Telegram, а уведомления путались бы.
    (
        "Telegram/SourceFiles/platform/win/windows_app_user_model_id.cpp",
        'const WCHAR AppUserModelIdBase[] = L"Telegram.TelegramDesktop.Store";',
        'const WCHAR AppUserModelIdBase[] = L"KiteGrams.KiteGramsDesktop.Store";',
    ),
    (
        "Telegram/SourceFiles/platform/win/windows_app_user_model_id.cpp",
        'const WCHAR AppUserModelIdBase[] = L"Telegram.TelegramDesktop";',
        'const WCHAR AppUserModelIdBase[] = L"KiteGrams.KiteGramsDesktop";',
    ),
    (
        "Telegram/SourceFiles/platform/win/windows_app_user_model_id.cpp",
        '\tQString path = systemShortcutPath() + u"Telegram.lnk"_q;',
        '\tQString path = systemShortcutPath() + u"KiteGrams.lnk"_q;',
    ),
    (
        "Telegram/SourceFiles/platform/win/windows_app_user_model_id.cpp",
        '\tconst auto installed = u"Telegram Desktop/Telegram.lnk"_q;\n'
        '\tconst auto old = u"Telegram Win (Unofficial)/Telegram.lnk"_q;\n'
        '\treturn validateShortcutAt(path + installed)\n'
        '\t\t|| validateShortcutAt(path + old);',
        '\t// KiteGrams: единственный ярлык, который нас интересует, — наш.\n'
        '\t// Наследные пути официального Telegram намеренно не проверяются:\n'
        '\t// чужой установленный клиент не должен считаться нашей установкой.\n'
        '\tconst auto installed = u"KiteGrams Desktop/KiteGrams.lnk"_q;\n'
        '\treturn validateShortcutAt(path + installed);',
    ),
    (
        "Telegram/SourceFiles/platform/win/windows_app_user_model_id.cpp",
        '\t\tpath += u"TelegramAlpha.lnk"_q;',
        '\t\tpath += u"KiteGramsAlpha.lnk"_q;',
    ),
    (
        "Telegram/SourceFiles/platform/win/windows_app_user_model_id.cpp",
        '\t\tpath += u"Telegram.lnk"_q;',
        '\t\tpath += u"KiteGrams.lnk"_q;',
    ),

    # --- 4. Ресурсы exe: то, что видно в «Свойствах файла» --------------------
    (
        "Telegram/Resources/winrc/Telegram.rc",
        '            VALUE "CompanyName", "Telegram FZ-LLC"',
        '            VALUE "CompanyName", "KiteGrams"',
    ),
    (
        "Telegram/Resources/winrc/Telegram.rc",
        '            VALUE "FileDescription", "Telegram Desktop"',
        '            VALUE "FileDescription", "KiteGrams Desktop"',
    ),
    (
        "Telegram/Resources/winrc/Telegram.rc",
        '            VALUE "ProductName", "Telegram Desktop"',
        '            VALUE "ProductName", "KiteGrams Desktop"',
    ),

    # --- 5. Имя exe ----------------------------------------------------------
    #
    # `output_name` задаёт OUTPUT_NAME цели Telegram, то есть имя файла. Нам
    # нужен KiteGrams.exe: он не конфликтует с Telegram.exe, и его находит
    # шаг `Locate the exe`.
    (
        "Telegram/CMakeLists.txt",
        '    set(output_name "Telegram")',
        '    set(output_name "KiteGrams")',
    ),

    # --- 6. Адрес сервера ----------------------------------------------------
    #
    # В tdesktop адрес DC — compile-time таблица. Наш сервер однодиапазонный
    # (`TELESRV_DC=2`, `TELESRV_STRICT_DC_CHECK=false` принимает любой ярлык DC
    # при обмене ключами), поэтому все пять DC указывают на один и тот же
    # адрес: на каком бы DC клиент ни стартовал, он попадёт к нам.
    #
    # После первого `help.getConfig` сервер присылает свой `dc_options`
    # (`internal/compat/tdesktop/config.go`), и клиент дальше пользуется им.
    (
        "Telegram/SourceFiles/mtproto/mtproto_dc_options.cpp",
        'const BuiltInDc kBuiltInDcs[] = {\n'
        '\t{ 1, "149.154.175.50" , 443 },\n'
        '\t{ 2, "149.154.167.51" , 443 },\n'
        '\t{ 2, "95.161.76.100"  , 443 },\n'
        '\t{ 3, "149.154.175.100", 443 },\n'
        '\t{ 4, "149.154.167.91" , 443 },\n'
        '\t{ 5, "149.154.171.5"  , 443 },\n'
        '};',
        'const BuiltInDc kBuiltInDcs[] = {\n'
        '\t{ 1, "' + SERVER_HOST + '", ' + str(SERVER_PORT) + ' },\n'
        '\t{ 2, "' + SERVER_HOST + '", ' + str(SERVER_PORT) + ' },\n'
        '\t{ 3, "' + SERVER_HOST + '", ' + str(SERVER_PORT) + ' },\n'
        '\t{ 4, "' + SERVER_HOST + '", ' + str(SERVER_PORT) + ' },\n'
        '\t{ 5, "' + SERVER_HOST + '", ' + str(SERVER_PORT) + ' },\n'
        '};',
    ),
    # Тестовая таблица (`-test`, `Environment::Test`) в релизной сборке не
    # выбирается никогда, но оставлять в бинарнике адреса официального
    # Telegram незачем: клиент, запущенный с `-test`, ушёл бы на чужой сервер.
    (
        "Telegram/SourceFiles/mtproto/mtproto_dc_options.cpp",
        'const BuiltInDc kBuiltInDcsTest[] = {\n'
        '\t{ 1, "149.154.175.10" , 443 },\n'
        '\t{ 2, "149.154.167.40" , 443 },\n'
        '\t{ 3, "149.154.175.117", 443 }\n'
        '};',
        'const BuiltInDc kBuiltInDcsTest[] = {\n'
        '\t{ 1, "' + SERVER_HOST + '", ' + str(SERVER_PORT) + ' },\n'
        '\t{ 2, "' + SERVER_HOST + '", ' + str(SERVER_PORT) + ' },\n'
        '\t{ 3, "' + SERVER_HOST + '", ' + str(SERVER_PORT) + ' }\n'
        '};',
    ),
    # IPv6-таблица официального Telegram остаётся, но в работу не идёт: у нашего
    # сервера IPv6 нет, и клиент не должен пытаться туда достучаться. Пустой
    # диапазон вместо правки самой таблицы — чтобы не ломать `array_size`
    # проверки и не заводить массив нулевой длины.
    (
        "Telegram/SourceFiles/mtproto/mtproto_dc_options.cpp",
        '\tconst auto listv6 = isTestMode()\n'
        '\t\t? gsl::make_span(kBuiltInDcsIPv6Test)\n'
        '\t\t: gsl::make_span(kBuiltInDcsIPv6).subspan(0);',
        '\t// KiteGrams: у нашего сервера нет IPv6-адреса, поэтому таблица IPv6\n'
        '\t// намеренно пуста — иначе клиент ходил бы на DC Telegram по IPv6.\n'
        '\tconst auto listv6 = isTestMode()\n'
        '\t\t? gsl::make_span(kBuiltInDcsIPv6Test)\n'
        '\t\t: gsl::make_span(kBuiltInDcsIPv6).subspan(0, 0);',
    ),

    # --- 7. Автообновление не должно вести на официальный Telegram -----------
    #
    # Если сервер не присылает `autoupdate_url_prefix`, tdesktop берёт адрес
    # отсюда — и по умолчанию это `https://td.telegram.org`, то есть обновление
    # официального клиента. Сборка идёт с `DESKTOP_APP_DISABLE_AUTOUPDATE=ON`,
    # так что код не компилируется вовсе; правка — вторая линия обороны на
    # случай, если автообновление когда-нибудь включат обратно.
    (
        "Telegram/SourceFiles/storage/localstorage.cpp",
        '\treturn AutoupdatePrefix("https://td.telegram.org");',
        '\treturn AutoupdatePrefix("' + PUBLIC_BASE_URL + '");',
    ),

    # --- 8. Видимое имя в интерфейсе -----------------------------------------
    #
    # Эти пять мест рисуют «Telegram Desktop» напрямую, мимо `AppName`.
    (
        "Telegram/SourceFiles/boxes/about_box.cpp",
        '\tbox->setTitle(u"Telegram Desktop"_q);',
        '\tbox->setTitle(u"KiteGrams Desktop"_q);',
    ),
    (
        "Telegram/SourceFiles/intro/intro_start.cpp",
        '\tsetTitleText(rpl::single(u"Telegram Desktop"_q));',
        '\tsetTitleText(rpl::single(u"KiteGrams Desktop"_q));',
    ),
    (
        "Telegram/SourceFiles/settings/sections/settings_notifications.cpp",
        '\t\tauto notifyTitle = st::msgNameFont->elided(u"Telegram Desktop"_q, rectForName.width());',
        '\t\tauto notifyTitle = st::msgNameFont->elided(u"KiteGrams Desktop"_q, rectForName.width());',
    ),
    (
        "Telegram/SourceFiles/window/notifications_manager_default.cpp",
        '\t\t\t? TextWithEntities{ u"Telegram Desktop"_q }',
        '\t\t\t? TextWithEntities{ u"KiteGrams Desktop"_q }',
    ),
    (
        "Telegram/SourceFiles/window/window_main_menu.cpp",
        '\t_telegram->setMarkedText(tr::link(\n'
        '\t\tu"Telegram Desktop"_q,\n'
        '\t\tu"https://desktop.telegram.org"_q));',
        '\t_telegram->setMarkedText(tr::link(\n'
        '\t\tu"KiteGrams Desktop"_q,\n'
        '\t\tu"' + PUBLIC_BASE_URL + '"_q));',
    ),

    # --- 9. Текст на экране входа --------------------------------------------
    (
        "Telegram/Resources/langs/lang.strings",
        '"lng_intro_about" = "Welcome to the official Telegram Desktop app.\\n'
        'It\'s fast and secure.";',
        '"lng_intro_about" = "Welcome to KiteGrams.\\n'
        'It\'s fast and secure.";',
    ),
]

# Что обязано остаться в overlay после сборки — по одному маркеру на смысл.
MARKERS = [
    ("бренд в version.h", "Telegram/SourceFiles/core/version.h",
     'constexpr auto AppName = "KiteGrams Desktop"_cs;'),
    ("имя exe", "Telegram/CMakeLists.txt", 'set(output_name "KiteGrams")'),
    ("адрес DC", "Telegram/SourceFiles/mtproto/mtproto_dc_options.cpp",
     '"' + SERVER_HOST + '", ' + str(SERVER_PORT)),
    ("AUMID", "Telegram/SourceFiles/platform/win/windows_app_user_model_id.cpp",
     'L"KiteGrams.KiteGramsDesktop"'),
    ("без официального автообновления", "Telegram/SourceFiles/storage/localstorage.cpp",
     'AutoupdatePrefix("' + PUBLIC_BASE_URL + '")'),
]

# Строки, которых в overlay быть не должно. `Telegram` как слово не проверяем:
# оно встречается в именах протокола, API и сотнях комментариев. Проверяем
# только то, что действительно означало бы «это официальный клиент».
FORBIDDEN = [
    (r"149\.154\.16[0-9]\.", "адрес DC официального Telegram"),
    (r"td\.telegram\.org", "адрес автообновления официального Telegram"),
    (r'AppName = "Telegram Desktop"', "имя приложения официального Telegram"),
    (r'L"Telegram\.TelegramDesktop', "AUMID официального Telegram"),
]


def newline_of(text):
    return "\r\n" if "\r\n" in text else "\n"


def read_normalized(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    return raw.decode("utf-8", errors="surrogateescape").replace("\r\n", "\n")


def write_normalized(path, text):
    """Пишем overlay всегда с LF: CI копирует его поверх клона как есть."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(text.encode("utf-8", errors="surrogateescape"))


def group_patches():
    result = {}
    for rel, old, new in PATCHES:
        result.setdefault(rel, []).append((old, new))
    return result


def build(src):
    if not os.path.isdir(os.path.join(src, "Telegram")):
        print("FAIL: нет дерева исходников в %s" % src)
        print("Подсказка: git clone --depth 1 -b dev "
              "https://github.com/iamxvbaba/gramsrv-tdesktop.git %s" % src)
        return 1

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)

    problems = []
    written = 0

    for rel, patches in sorted(group_patches().items()):
        source = os.path.join(src, rel.replace("/", os.sep))
        if not os.path.isfile(source):
            problems.append("%s: файла нет в базе" % rel)
            continue
        text = read_normalized(source)
        for index, (old, new) in enumerate(patches, start=1):
            count = text.count(old)
            if count != 1:
                problems.append(
                    "%s: правка #%d нашлась %d раз(а), ожидалось ровно 1:\n"
                    "      %s" % (rel, index, count, old.replace("\n", "\n      "))
                )
                continue
            text = text.replace(old, new, 1)
        if problems:
            # Файл уже мог быть частично пропатчен — не пишем его вовсе.
            if any(item.startswith(rel + ":") for item in problems):
                continue
        write_normalized(os.path.join(OUT, rel.replace("/", os.sep)), text)
        written += 1

    if problems:
        print("FAIL: правки не наложились:")
        for item in problems:
            print("   %s" % item)
        print("\nСкорее всего база уехала вперёд. Обнови BASE_REF и якоря.")
        return 1

    print("файлов в overlay : %d" % written)
    print("правок применено : %d" % len(PATCHES))

    bad = check()
    if bad:
        print("\nFAIL: overlay не прошёл проверку:")
        for item in bad:
            print("   %s" % item)
        return 1

    print("\noverlay готов: %s" % OUT)
    print("Дальше: set_server_key.py --source %s --pem <server_rsa_public.pem>"
          % os.path.join(OUT, "Telegram", "SourceFiles", "mtproto",
                         "mtproto_dc_options.cpp"))
    return 0


def check():
    problems = []

    for label, rel, marker in MARKERS:
        path = os.path.join(OUT, rel.replace("/", os.sep))
        if not os.path.isfile(path):
            problems.append("%s: файла нет в overlay (%s)" % (rel, label))
            continue
        if marker not in read_normalized(path):
            problems.append("%s: нет маркера «%s»" % (rel, label))

    for root, _, names in os.walk(OUT):
        for name in names:
            path = os.path.join(root, name)
            rel = os.path.relpath(path, OUT).replace(os.sep, "/")
            if not rel.lower().endswith((
                    ".cpp", ".h", ".hpp", ".txt", ".strings", ".rc", ".cmake")):
                continue
            text = read_normalized(path)
            for pattern, what in FORBIDDEN:
                if re.search(pattern, text):
                    problems.append("%s: остался %s" % (rel, what))

    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", default=DEFAULT_SRC,
                        help="локальный клон gramsrv-tdesktop")
    parser.add_argument("--check", action="store_true",
                        help="только проверить готовый overlay")
    args = parser.parse_args()

    if args.check:
        if not os.path.isdir(OUT):
            print("FAIL: overlay не собран (%s)" % OUT)
            return 1
        problems = check()
        if problems:
            print("FAIL: overlay не прошёл проверку:")
            for item in problems:
                print("   %s" % item)
            return 1
        print("overlay чист.")
        return 0

    return build(os.path.normpath(args.src))


if __name__ == "__main__":
    sys.exit(main())
