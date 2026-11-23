#!/usr/bin/env python3
import datetime
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_JSON = REPO_ROOT / "repo.json"
ICONS_ZIP = REPO_ROOT / "icons.zip"

FIELDS = ["title", "author", "version", "description", "details", "license", "changelog"]
ICON_EXTS = [".png", ".jpg", ".jpeg"]


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ouncebrew-repo-updater"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def fetch_json(url: str):
    return json.loads(fetch_bytes(url).decode("utf-8"))


def fetch_icon(direct_url: str):
    base = direct_url.rstrip("/")
    for ext in ICON_EXTS:
        url = base + "/icon" + ext
        try:
            data = fetch_bytes(url)
            if data:
                return ext, data
        except Exception as e:
            print(f"[icon-skip] {url} ({e})")
    return None, None


def main() -> int:
    data = json.loads(REPO_JSON.read_text(encoding="utf-8"))
    packages = data.get("packages", [])
    changed = False
    icon_entries = {}
    # Versions before this run, to detect releases (version bumps).
    data_versions = {p.get("name"): p.get("version") for p in packages}

    for pkg in packages:
        direct_url = (pkg.get("direct_url") or pkg.get("url") or "").rstrip("/")
        name = pkg.get("name", "?")

        if pkg.get("file") and direct_url:
            pkg_json_url = direct_url + "/package.json"
            try:
                remote = fetch_json(pkg_json_url)
                if isinstance(remote, dict):
                    for field in FIELDS:
                        value = remote.get(field)
                        if isinstance(value, str) and value != pkg.get(field):
                            print(f"[update] {name}.{field}")
                            pkg[field] = value
                            changed = True
                else:
                    print(f"[skip] {name}: package.json is not an object")
            except Exception as e:
                print(f"[skip] {name}: {pkg_json_url} ({e})")

            ext, icon_data = fetch_icon(direct_url)
            if ext and icon_data:
                icon_entries[f"{name}/icon{ext}"] = icon_data
                print(f"[icon] {name}/icon{ext}")

    # Stamp UpdateDateTime ("DD/MM/YYYY HH:MM", 24hr UTC) when the version
    # changed or no stamp exists yet.
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%d/%m/%Y %H:%M")
    for pkg in packages:
        if not pkg.get("file"):
            continue
        if pkg.get("version") != data_versions.get(pkg.get("name")) or not pkg.get("UpdateDateTime"):
            pkg["UpdateDateTime"] = now
            print(f"[update] {pkg.get('name', '?')}.UpdateDateTime")
            changed = True

    if changed:
        REPO_JSON.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
        print("repo.json updated")
    else:
        print("no repo.json changes")

    if icon_entries:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for arcname, content in sorted(icon_entries.items()):
                zf.writestr(arcname, content)
        new_zip = buf.getvalue()
        old_zip = ICONS_ZIP.read_bytes() if ICONS_ZIP.exists() else b""
        if new_zip != old_zip:
            ICONS_ZIP.write_bytes(new_zip)
            print("icons.zip updated")
        else:
            print("no icons.zip changes")
    else:
        print("no icons found")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
