#!/usr/bin/env python3
"""Qt 6.11 + MSVC: явный формат PDB для стадии `Libraries`.

`configure -force-debug-info` заставляет Qt собирать RelWithDebInfo, но
`CMAKE_MSVC_DEBUG_INFORMATION_FORMAT` остаётся пустым. Тогда cl.exe получает
`/Fd` без пути и падает на `mocs_compilation_RelWithDebInfo.cpp`:

    fatal error C1083: Cannot open compiler generated file: '' : Invalid argument

Скрипт добавляет `-D CMAKE_MSVC_DEBUG_INFORMATION_FORMAT=ProgramDatabase` в
блок конфигурации Qt 6 (единственная строка с LCMS2_LIBRARIES). Идемпотентен:
повторный запуск ничего не меняет.
"""
import sys

MARKER = "CMAKE_MSVC_DEBUG_INFORMATION_FORMAT=ProgramDatabase"
ANCHOR = '-D LCMS2_LIBRARIES="%LCMS2_DIR%\\\\out\\\\Release\\\\src\\\\liblcms2.a"'


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_prepare_qt_pdb.py <prepare.py>", file=sys.stderr)
        return 2
    path = sys.argv[1]
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    if MARKER in text:
        print("already patched")
        return 0
    count = text.count(ANCHOR)
    if count != 1:
        print(f"anchor count = {count}, want 1", file=sys.stderr)
        return 1
    patched = text.replace(ANCHOR, ANCHOR + " ^\n        -D " + MARKER, 1)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(patched)
    print("patched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
