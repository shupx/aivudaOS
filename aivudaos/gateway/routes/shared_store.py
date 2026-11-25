import tempfile
from urllib.parse import quote

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from aivudaos.core.apps import sharing
from aivudaos.gateway.routes.apps import _require_auth


router = APIRouter(prefix="/api/shared-apps", tags=["shared-apps"])


@router.post("")
def create_share(token: str):
    _require_auth(token)
    return {"path": "/aivuda_os/api/shared-apps/" + sharing.issue_share()}


def require_share(key: str, response: Response):
    response.headers["Cache-Control"] = "no-store"
    if not sharing.share_is_valid(key):
        raise HTTPException(403, "Sharing link is invalid or expired")


store = APIRouter(prefix="/{key}/aivuda_app_store/store", dependencies=[Depends(require_share)])
# Keep cross-origin access confined to the read-only store.
shared_store = FastAPI(openapi_url=None)
shared_store.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["GET"],
    expose_headers=["Content-Disposition"],
)


@store.get("/index")
def index():
    latest = {}
    for release in sharing.installed_releases():
        latest.setdefault(release["app_id"], release)
    return {"items": list(latest.values())}


@store.get("/apps/{app_id}")
def details(app_id: str):
    releases = sharing.installed_releases(app_id)
    if not releases:
        raise HTTPException(404, "App not installed")
    versions = [
        {"version": item["version"], "updated_at": item["updated_at"],
         "description": item["manifest"]["description"], "status": "published"}
        for item in releases
    ]
    return {"app": releases[0]["manifest"], "versions": versions}


@store.get("/apps/{app_id}/versions/{version}/download-url")
def download_info(app_id: str, version: str):
    size = build_package(app_id, version)
    return {
        "url": "/store/apps/{}/versions/{}/download".format(quote(app_id, safe=""), quote(version, safe="")),
        "size": size, "filename": "{}-{}.tar".format(app_id, version),
    }


def build_package(app_id, version, output=None):
    try:
        return sharing.package_version(app_id, version, output)
    except FileNotFoundError:
        raise HTTPException(404, "Installed version or package files not found")
    except OSError:
        raise HTTPException(409, "Unable to read installed package files")


@store.get("/apps/{app_id}/versions/{version}/download")
def download(app_id: str, version: str):
    package = tempfile.TemporaryFile()
    try:
        build_package(app_id, version, package)
        size = package.tell()
        package.seek(0)
        filename = quote("{}-{}.tar".format(app_id, version), safe="")
        return StreamingResponse(
            iter(lambda: package.read(256 * 1024), b""),
            media_type="application/x-tar",
            headers={
                "Content-Length": str(size),
                "Content-Disposition": "attachment; filename*=UTF-8''" + filename,
                "Cache-Control": "no-store",
            },
            background=BackgroundTask(package.close),
        )
    except BaseException:
        package.close()
        raise


shared_store.include_router(store)
