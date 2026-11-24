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

FIELDS = ["title", "author", "description", "details", "license", "changelog"]
LIST_FIELDS = ["requiredDeletion", "userDeletion"]
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


def _version_segments(s: str):
    """Parse 1-4 leading numeric segments (optional 'v', trailing suffix ignored).
    Returns zero-padded 4-list, or None if invalid."""
    s = s.strip()
    if s[:1].lower() == "v":
        s = s[1:]
    segs = []
    for part in s.split("."):
        j = 0
        while j < len(part) and part[j].isdigit():
            j += 1
        if j == 0:
            break  # no digits: suffix reached (or invalid if first)
        if j > 9:
            return None
        segs.append(int(part[:j]))
        if len(segs) > 4:
            return None
        if j < len(part):
            break  # trailing suffix: stop here
    if not segs:
        return None
    while len(segs) < 4:
        segs.append(0)
    return segs


def compare_versions(a: str, b: str) -> int:
    sa, sb = _version_segments(a or ""), _version_segments(b or "")
    if sa is not None and sb is not None:
        return (sa > sb) - (sa < sb)
    return 0 if a == b else 1


def versions_equal(a: str, b: str) -> bool:
    return compare_versions(a, b) == 0


def main() -> int:
    data = json.loads(REPO_JSON.read_text(encoding="utf-8"))
    packages = data.get("packages", [])
    changed = False
    icon_entries = {}
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%d/%m/%Y %H:%M")

    for pkg in packages:
        direct_url = (pkg.get("direct_url") or pkg.get("url") or "").rstrip("/")
        name = pkg.get("name", "?")

        if pkg.get("file") and direct_url:
            pkg_json_url = direct_url + "/package.json"
            version_changed = False
            remote = None
            try:
                remote = fetch_json(pkg_json_url)
                if isinstance(remote, dict):
                    for field in FIELDS:
                        value = remote.get(field)
                        if isinstance(value, str) and value != pkg.get(field):
                            print(f"[update] {name}.{field}")
                            pkg[field] = value
                            changed = True
                    for field in LIST_FIELDS:
                        value = remote.get(field)
                        if isinstance(value, list) and all(isinstance(x, str) for x in value):
                            if value != pkg.get(field):
                                print(f"[update] {name}.{field}")
                                pkg[field] = value
                                changed = True
                    new_ver = remote.get("version")
                    if isinstance(new_ver, str) and new_ver != pkg.get("version"):
                        if versions_equal(new_ver, pkg.get("version") or ""):
                            pass  # same version, different spelling — leave repo string alone
                        else:
                            print(f"[update] {name}.version")
                            pkg["version"] = new_ver
                            changed = True
                            version_changed = True
                else:
                    print(f"[skip] {name}: package.json is not an object")
            except Exception as e:
                print(f"[skip] {name}: {pkg_json_url} ({e})")
                new_ver = None
                version_changed = False

            if version_changed or not pkg.get("UpdateDateTime"):
                # Prefer the release's own date; fall back to runner time.
                stamp = now
                if isinstance(remote, dict):
                    rd = remote.get("date")
                    if isinstance(rd, str):
                        try:
                            datetime.datetime.strptime(rd.strip(), "%d/%m/%Y %H:%M")
                            stamp = rd.strip()
                        except ValueError:
                            pass
                pkg["UpdateDateTime"] = stamp
                print(f"[update] {name}.UpdateDateTime")
                changed = True

            ext, icon_data = fetch_icon(direct_url)
            if ext and icon_data:
                icon_entries[f"{name}/icon{ext}"] = icon_data
                print(f"[icon] {name}/icon{ext}")

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
