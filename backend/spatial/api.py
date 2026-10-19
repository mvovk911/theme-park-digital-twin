"""HTTP installation for independent, read-only spatial design queries."""
from pathlib import Path

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .contracts import MAX_REQUEST_BYTES, RouteRequest, Variant
from .service import ROOT, SpatialQueryError, SpatialService, _json
from .previews import PreviewUnavailable, SpatialPreviews


def install_spatial_routes(app, *, project_root: Path = ROOT):
    """Verify immutable source snapshots before exposing any endpoints.

    No database, live-state lock, replay access, action service, or renderer state
    is read or changed. A hash mismatch raises SpatialIdentityError and installs
    no routes; the caller must fail startup rather than serve an unverified graph.
    """
    if getattr(app.state, 'spatial_installed', False):
        raise ValueError('Spatial routes have already been installed')
    service = SpatialService(project_root)
    previews = SpatialPreviews(project_root, service)

    def preview(variant):
        try:
            return previews.get(variant)
        except PreviewUnavailable as exc:
            raise HTTPException(503, {'code': 'spatial_preview_unavailable', 'message': str(exc)}) from None

    @app.get('/api/spatial/previews/{variant}')
    def spatial_preview(variant: Variant):
        image, metadata, headers = preview(variant)
        return Response(image, media_type='image/png', headers=headers)

    @app.get('/api/spatial/previews/{variant}/metadata')
    def spatial_preview_metadata(variant: Variant):
        image, metadata, headers = preview(variant)
        return JSONResponse(metadata, headers=headers)

    @app.get('/api/spatial/capabilities')
    def spatial_capabilities():
        return service.capabilities()

    @app.get('/api/spatial/graphs/{variant}')
    def spatial_graph(variant: Variant):
        return service.graph(variant)

    @app.post('/api/spatial/route', openapi_extra={
        'requestBody': {'required': True, 'content': {'application/json': {'schema': RouteRequest.model_json_schema()}}}
    })
    async def spatial_route(request: Request):
        content_type = request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
        if content_type != 'application/json':
            raise HTTPException(415, {'code': 'spatial_json_required', 'message': 'Use application/json'})
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                raise HTTPException(413, {'code': 'spatial_request_too_large', 'message': 'Spatial request exceeds 16 KiB'})
            body.extend(chunk)
        try:
            data = _json(bytes(body))
            query = RouteRequest.model_validate(data)
        except ValidationError as exc:
            raise HTTPException(422, {'code': 'invalid_spatial_request',
                                      'errors': exc.errors(include_url=False, include_context=False, include_input=False)}) from None
        except (ValueError, UnicodeError, RecursionError):
            raise HTTPException(422, {'code': 'invalid_spatial_json',
                                      'message': 'Expected finite JSON with unique keys'}) from None
        try:
            return service.route(query)
        except SpatialQueryError as exc:
            raise HTTPException(422, {'code': 'invalid_spatial_query', 'message': str(exc)}) from None

    app.state.spatial_installed = True
    return service
