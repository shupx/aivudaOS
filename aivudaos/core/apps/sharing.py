"""Read-only distribution of installed versions through the store protocol."""

import hashlib
import json
import os
import secrets
import stat
import tarfile
import time
from contextlib import ExitStack
from pathlib import Path

from aivudaos.core.db.connection import db_conn
from aivudaos.core.paths import APPS_DIR


def issue_share():
    key = secrets.token_urlsafe(32)
    digest = hashlib.sha256(key.encode()).hexdigest()
    with db_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_share (id, digest, expires) VALUES (1, ?, ?)",
            (digest, int(time.time()) + 3600),
        )
    return key


def share_is_valid(key):
    with db_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM app_share WHERE digest = ? AND expires > ?",
            (hashlib.sha256(key.encode()).hexdigest(), int(time.time())),
        ).fetchone() is not None


def installed_releases(app_id=None):
    query = "SELECT app_id, version, installed_at, manifest FROM app_installation WHERE status = 'installed'"
    params = ()
    if app_id is not None:
        query += " AND app_id = ?"
        params = (app_id,)
    with db_conn() as conn:
        rows = conn.execute(query + " ORDER BY installed_at DESC, version DESC", params).fetchall()
    releases = []
    for row in rows:
        manifest = json.loads(row["manifest"] or "{}") or {}
        releases.append({
            "app_id": row["app_id"], "version": row["version"], "updated_at": row["installed_at"],
            "manifest": {"name": manifest.get("name") or row["app_id"],
                         "description": manifest.get("description") or ""},
        })
    return releases


def package_version(app_id, version, output=None):
    """Measure or write exactly the same uncompressed PAX tar format."""
    for part in (app_id, version):
        if not part or part in (".", "..") or Path(part).name != part:
            raise FileNotFoundError("Invalid installed version")
    with db_conn() as conn:
        row = conn.execute(
            "SELECT install_path FROM app_installation WHERE app_id=? AND version=? AND status='installed'",
            (app_id, version),
        ).fetchone()
    root = APPS_DIR / app_id / "versions" / version
    if row is None or Path(row["install_path"]) != root:
        raise FileNotFoundError("Version not installed")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as stack:
        fd = os.open(str(APPS_DIR), directory_flags)
        stack.callback(os.close, fd)
        for part in (app_id, "versions", version):
            fd = os.open(part, directory_flags, dir_fd=fd)
            stack.callback(os.close, fd)
        archive = None
        if output is not None:
            archive = stack.enter_context(tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT))
        length = 0
        has_manifest = False
        for path, dirs, files, parent in os.fwalk(".", dir_fd=fd, onerror=_raise_walk_error):
            for name in sorted(dirs + files):
                entry = os.stat(name, dir_fd=parent, follow_symlinks=False)
                member = _tar_member(root, path, name, parent, entry)
                if member is None:
                    continue
                if member.name in ("manifest.yaml", "manifest.yml") and member.isfile():
                    has_manifest = True
                length += len(member.tobuf(tarfile.PAX_FORMAT)) + ((member.size + 511) // 512) * 512
                if archive is not None:
                    _write_member(archive, member, parent, name, entry)
        if not has_manifest:
            raise FileNotFoundError("Installed version has no manifest")
    # tarfile writes two end markers, then pads to a full record.
    block = tarfile.RECORDSIZE
    return ((length + 1024 + block - 1) // block) * block


def _raise_walk_error(exc):
    raise exc


def _tar_member(root, path, name, parent, entry):
    member = tarfile.TarInfo(str(Path(path) / name))
    member.mode = stat.S_IMODE(entry.st_mode) & 0o777
    member.mtime = int(entry.st_mtime)
    if stat.S_ISDIR(entry.st_mode):
        member.type = tarfile.DIRTYPE
    elif stat.S_ISREG(entry.st_mode):
        member.size = entry.st_size
    elif stat.S_ISLNK(entry.st_mode):
        target = os.readlink(name, dir_fd=parent)
        if os.path.isabs(target):
            return None
        try:
            resolved = (root / path / target).resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            return None
        member.type = tarfile.SYMTYPE
        member.linkname = os.path.relpath(str(resolved), str(root / path))
    else:
        return None
    return member


def _write_member(archive, member, parent, name, entry):
    if not member.isfile():
        archive.addfile(member)
        return
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(name, flags, dir_fd=parent), "rb") as source:
        opened = os.fstat(source.fileno())
        if not os.path.samestat(entry, opened) or opened.st_size != member.size:
            raise OSError("Installed version changed while packaging")
        archive.addfile(member, source)
