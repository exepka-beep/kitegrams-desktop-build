# KiteGrams Desktop — конвейер сборки

Сборка ПК-клиента KiteGrams (Windows x64) через GitHub Actions.

Клиент — форк `iamxvbaba/gramsrv-tdesktop` (это форк официального
`telegramdesktop/tdesktop` 7.3.1, подогнанный под наш серверный стек
gramsrv/telesrv). Собирается на `windows-2022` из закреплённого коммита, поверх
которого накладывается overlay из `files/`.

## Что даёт сборка

`KiteGrams-portable-win64.zip` — переносимая сборка: `KiteGrams.exe` плюс
`modules/x64/d3d/d3dcompiler_47.dll`. Qt и остальные библиотеки слинкованы
статически, поэтому больше ничего не нужно: распаковал — запустил.

Данные клиент хранит в `tdata` рядом с exe (на Windows Release-сборка сначала
пробует папку exe и уходит в `%APPDATA%` только если она недоступна на запись).
Официальный Telegram живёт в `%APPDATA%\Telegram Desktop` и имеет свой AUMID,
поэтому две установки не пересекаются.

## Чем клиент отличается от официального Telegram

| Что | Где | Значение |
|---|---|---|
| Адрес DC | `mtproto/mtproto_dc_options.cpp` | `2.26.81.165:2398`, все DC 1–5 |
| Публичный RSA-ключ сервера | там же | подставляется на сборке из `/owpengram/server-info` |
| Имя приложения | `core/version.h` | `KiteGrams Desktop` |
| Имя exe | `Telegram/CMakeLists.txt` | `KiteGrams.exe` |
| AppUserModelID | `platform/win/windows_app_user_model_id.cpp` | `KiteGrams.KiteGramsDesktop` |
| Автообновление | флаг CMake | выключено (`DESKTOP_APP_DISABLE_AUTOUPDATE=ON`) |

Автообновление выключено намеренно. TDesktop берёт адрес обновлений из
`help.getConfig.autoupdate_url_prefix`, а если сервер его не прислал — из
`storage/localstorage.cpp`, где по умолчанию `https://td.telegram.org`. То есть
с включённым автообновлением клиент скачал бы и поставил себе официальный
Telegram. С выключенным — `UpdateChecker` вырезается препроцессором, цель
`Updater` не создаётся вовсе, подменить exe некому.

## Overlay

`files/` — это готовые файлы, которые копируются поверх клона базы. Не
`.patch`: патчи ломаются на любом сдвиге контекста, а overlay либо ложится
целиком, либо падает на шаге проверки брендинга.

Собран скриптом `scripts/make_overlay.py` из локального клона базы. Скрипт
падает, если якорь правки не найден ровно один раз: молча пропустить правку
нельзя — иначе соберётся клиент с адресом официального Telegram.

Пересобрать после обновления базы:

```sh
git clone --depth 1 -b dev https://github.com/iamxvbaba/gramsrv-tdesktop.git ../_tdesktop_src
python scripts/make_overlay.py --src ../_tdesktop_src
python scripts/set_server_key.py \
  --source files/Telegram/SourceFiles/mtproto/mtproto_dc_options.cpp \
  --pem ../keys/server_rsa_public.pem
```

Коммит базы закреплён в двух местах — `BASE_REF` в `make_overlay.py` и
`UPSTREAM_REF` в воркфлоу. Менять их надо вместе.

## Скрипты

| Скрипт | Что делает |
|---|---|
| `make_overlay.py` | собирает `files/` из клона базы; `--check` проверяет готовый overlay |
| `set_server_key.py` | вшивает PEM сервера в `kPublicRSAKeys`; `--check` сверяет |
| `bake_server_key.py` | скачивает ключ с `/owpengram/server-info` |
| `scan_exe.py` | ищет в собранном exe нужные и запрещённые строки (UTF-8 и UTF-16LE) |

## Запуск

Actions → **Build KiteGrams desktop** → Run workflow. Прогон идёт ~2–3 часа:
стадия `Libraries` (32 библиотеки + Qt из исходников) занимает около 40 минут на
холодном кэше, дальше сама сборка. Кэши `ThirdParty`, `Libraries` и `Qt`
переживают прогоны, поэтому повторные сборки заметно быстрее.

Параметр `parallel` по умолчанию 2: три сгенерированных `qrc_emoji_*.cpp`
(~85k строк литералов) при большем параллелизме роняют `cl.exe` в
`C1060: compiler is out of heap space` на 16-гигабайтном раннере.

## Проверки в конце сборки

* `scan_exe.py` — в exe есть `KiteGrams` и `2.26.81.165`, нет `149.154.*`,
  `td.telegram.org` и AUMID официального Telegram;
* `set_server_key.py --check` — ключ в exe совпадает с тем, что отдаёт сервер;
* шаг `Verify branding` до сборки — те же проверки по исходникам, чтобы не
  тратить 40 минут на заведомо неверный overlay.
