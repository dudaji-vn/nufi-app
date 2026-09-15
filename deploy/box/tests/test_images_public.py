#!/usr/bin/env python3
"""Every image the box pulls must be pullable by a stranger.

apps/docs/content/docs/box/install.mdx tells the public to fetch `deploy/box`
and run the installer, and the installer runs no `docker login` and carries no
token. So that page is true only for as long as every NuFi image the box pulls
is anonymously readable on GHCR.

Two of them were private when the guide was written (`nufi-chat` and
`nufi-admin`), which would have made the published instructions fail at the
first `docker pull` on any machine that had not already logged in to GHCR for
other reasons. A developer machine cannot notice this: it is logged in.

Network test, on purpose. There is no offline way to ask GitHub whether a
package is public, and the alternative is a documentation page that quietly
stops being true.

Run:  python3 tests/test_images_public.py     (exit 0 = PASS)
"""
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

BOX = pathlib.Path(__file__).resolve().parents[1]
OWNER = "dudaji-vn"


def images_the_box_pulls():
    """The NuFi images named in docker-compose.yml, as bare package names."""
    text = (BOX / "docker-compose.yml").read_text()
    found = set()
    for line in text.splitlines():
        m = re.search(r"NUFI_REGISTRY:-ghcr\.io/dudaji-vn\}/([a-z0-9-]+):", line)
        if m:
            found.add(m.group(1))
    return sorted(found)


def is_public(package):
    """Anonymous read of the tag list, the same way a stranger's docker pull starts."""
    token_url = (f"https://ghcr.io/token?scope=repository:{OWNER}/{package}:pull"
                 f"&service=ghcr.io")
    try:
        with urllib.request.urlopen(token_url, timeout=30) as r:
            token = json.load(r).get("token", "")
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"could not reach ghcr.io: {exc}")
    req = urllib.request.Request(f"https://ghcr.io/v2/{OWNER}/{package}/tags/list")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200, r.status
    except urllib.error.HTTPError as exc:
        return False, exc.code
    except (urllib.error.URLError, OSError) as exc:
        raise SystemExit(f"could not reach ghcr.io: {exc}")


def main():
    packages = images_the_box_pulls()
    assert packages, "no NuFi images found in docker-compose.yml — has the image line changed?"
    private = []
    for package in packages:
        public, code = is_public(package)
        print(f"  {'public ' if public else 'PRIVATE'}  {OWNER}/{package}  (HTTP {code})")
        if not public:
            private.append(package)
    if private:
        print()
        print("These are private, so the published install guide does not work for")
        print("anyone outside the org — the installer runs no docker login:")
        for package in private:
            print(f"  https://github.com/orgs/{OWNER}/packages/container/{package}/settings")
        sys.exit(1)
    print(f"PASS: all {len(packages)} NuFi images the box pulls are public")


if __name__ == "__main__":
    main()
