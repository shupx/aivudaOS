"""Authenticated startup pipeline endpoints, mounted before dynamic app routes."""
from contextlib import contextmanager
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StrictStr

from aivudaos.core.apps.pipeline import PipelineConflict
from aivudaos.core.errors import AppOperationConflictError, AppRuntimeError
from aivudaos.gateway.deps import get_pipeline_service
from aivudaos.gateway.routes.apps import _require_auth

router = APIRouter(prefix='/api/apps/pipeline', tags=['apps'], dependencies=[Depends(_require_auth)])


class PipelineSelection(BaseModel, extra='forbid'):
    profile: Optional[StrictStr] = None
    group_id: Optional[StrictStr] = None


@contextmanager
def pipeline_errors():
    try:
        yield
    except (PipelineConflict, AppOperationConflictError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except AppRuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(500, 'Could not access the startup pipeline configuration') from exc


@router.get('')
def get_startup_pipeline(view: Optional[Literal['list']] = None):
    """Read the pipeline configuration and operation. Use view=list to omit inventory and validation."""
    with pipeline_errors():
        return get_pipeline_service().describe(list_view=view == 'list')


@router.put('')
def save_startup_pipeline(config: Dict[str, Any]):
    """Replace the configuration if its version still matches."""
    with pipeline_errors():
        return get_pipeline_service().save(config)


@router.post('/validate')
def validate_startup_pipeline(config: Dict[str, Any]):
    """Validate a draft and preview its batches without saving or running it."""
    with pipeline_errors():
        return get_pipeline_service().validate(config)


def _queue(action, selection):
    with pipeline_errors():
        return get_pipeline_service().queue(action, selection.profile if selection else None,
                                             selection.group_id if selection else None)


@router.post('/run', status_code=202)
def run_startup_pipeline(selection: Optional[PipelineSelection] = None):
    """Queue a saved profile or one group; omit selection to run the default profile."""
    return _queue('run', selection)


@router.post('/stop', status_code=202)
def stop_startup_pipeline(selection: Optional[PipelineSelection] = None):
    """Stop a profile or one group in reverse dependency order."""
    return _queue('stop', selection)


@router.post('/restart', status_code=202)
def restart_startup_pipeline(selection: Optional[PipelineSelection] = None):
    """Stop, then start a profile or one group under the same cancellable operation."""
    return _queue('restart', selection)
