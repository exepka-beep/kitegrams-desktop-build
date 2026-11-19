#!/usr/bin/env python3
"""Qt 6.11 + MSVC: убираем `-force-debug-info` из стадии `Libraries`.

Почему. `configure -force-debug-info` переводит Release-сборку Qt в
RelWithDebInfo и заставляет cl.exe писать PDB. На этой связке (Qt 6.11.2,
MSVC 14.44, Ninja) сборка `qtmultimedia` падает на

    DeviceDiscoverySupportPrivate_autogen/mocs_compilation_RelWithDebInfo.cpp
    fatal error C1083: Cannot open compiler generated file: ''

Явный `-D CMAKE_MSVC_DEBUG_INFORMATION_FORMAT=ProgramDatabase` подставлял
корректный `/Fdqtbase\\lib\\Qt6DeviceDiscoverySupport.pdb`, но ошибка
повторялась — путь относительный, а каталога `qtbase\\lib` на момент
компиляции ещё нет, и cl.exe печатает пустое имя файла.

Отладочные символы Qt нам не нужны: crash reports в сборке выключены
(`DESKTOP_APP_DISABLE_CRASH_REPORTS=ON`), а exe собирается со своим PDB.
Без `-force-debug-info` Qt собирается обычным Release (`/O2 /DNDEBUG`, без
/Zi и /Fd) — это и быстрее, и без C1083.

Скрипт также убирает строку `-D CMAKE_MSVC_DEBUG_INFORMATION_FORMAT=...`,
которую добавляла предыдущая версия патча. Идемпотентен.
"""
import re
import sys

STALE = "-D CMAKE_MSVC_DEBUG_INFORMATION_FORMAT=ProgramDatabase"
FORCE = re.compile(r"^[ \t]*-force-debug-info[ \t]*[\^\\][ \t]*\r?\n", re.M)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_prepare_qt_pdb.py <prepare.py>", file=sys.stderr)
        return 2
    path = sys.argv[1]
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    changed = False
    if STALE in text:
        text = text.replace(" ^\n        " + STALE, "", 1)
        text = text.replace(STALE, "", 1)
        changed = True
        print("убрана строка ProgramDatabase от прошлого патча")

    text, removed = FORCE.subn("", text)
    if removed:
        changed = True
        print(f"убрано -force-debug-info: {removed}")

    if not changed:
        print("already patched")
        return 0

    if "-force-debug-info" in text:
        print("ВНИМАНИЕ: остались вхождения -force-debug-info в других формах",
              file=sys.stderr)

    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print("patched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
