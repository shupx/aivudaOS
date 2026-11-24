def include_business_routes(app, prefix=""):
    """Mount public business routes in the same order for HTTP and the MCP schema."""
    from aivudaos.gateway.routes import apps, auth, config, pipeline

    # The static pipeline endpoints must precede the dynamic app routes.
    for router in (auth.router, config.router, pipeline.router, apps.router):
        app.include_router(router, prefix=prefix)
