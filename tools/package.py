#!/usr/bin/env python3
"""Explicit source allowlist: local configuration, sessions and topics never ship."""

import hashlib
import gzip
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def package():
    files = [ROOT / "README.md", ROOT / ".gitignore", ROOT / "config.example.json", ROOT / "config.direct.example.json"]
    for folder, pattern in (("roblox_presence", "*.py"), ("tests", "*.py"),
                            ("deploy", "*.py"), ("deploy", "*.service"), ("docs", "*.md"),
                            ("tools", "*.py"), ("tools", "*.cjs"), ("tests", "*.cjs"),
                            ("deploy", "*.openrc")):
        files.extend(sorted((ROOT / folder).glob(pattern)))
    files = sorted(set(files))
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    archive = output / "roblox-presence-0.1.0.tar.gz"
    with archive.open("wb") as output_stream:
        with gzip.GzipFile(filename="", fileobj=output_stream, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as tar:
                for path in files:
                    if path.is_symlink() or not path.is_file():
                        raise ValueError("Release inputs must be regular source files, not symlinks")
                    info = tar.gettarinfo(str(path), arcname="roblox-presence/" + str(path.relative_to(ROOT)))
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = 0
                    info.mode = 0o755 if path.suffix == ".openrc" else 0o644
                    with path.open("rb") as stream:
                        tar.addfile(info, stream)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / (archive.name + ".sha256")).write_text(digest + "  " + archive.name + "\n")
    print(f"{archive}\nSHA256 {digest}")


if __name__ == "__main__":
    package()
