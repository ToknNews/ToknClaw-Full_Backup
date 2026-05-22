#!/usr/bin/env python3

import os

ROOT_DIR = "/opt/toknclaw"

def fix_file(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # find shebang
    shebang_index = None
    for i, line in enumerate(lines):
        if line.startswith("#!"):
            shebang_index = i
            break

    if shebang_index is None:
        return False  # no shebang, ignore

    # already correct
    if shebang_index == 0:
        return False

    shebang = lines.pop(shebang_index)

    # remove leading blank lines after removal
    while lines and lines[0].strip() == "":
        lines.pop(0)

    # rebuild
    new_lines = [shebang, "\n"] + lines

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    return True


def main():
    fixed = 0

    for root, _, files in os.walk(ROOT_DIR):
        for file in files:
            if not file.endswith(".py"):
                continue

            path = os.path.join(root, file)

            try:
                if fix_file(path):
                    print(f"[FIXED] {path}")
                    fixed += 1
            except Exception as e:
                print(f"[ERROR] {path}: {e}")

    print(f"\nDone. Fixed {fixed} files.")


if __name__ == "__main__":
    main()
