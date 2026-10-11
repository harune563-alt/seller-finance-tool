"""Normalize only configured, exact ingress aliases; never trust destination headers as Origin."""
class OriginAliasMiddleware:
    def __init__(self, app, aliases):
        self.app = app
        self.aliases = {source.encode("latin-1"): target.encode("latin-1") for source, target in aliases.items()}

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = {**scope, "headers": [
                (key, self.aliases.get(value, value) if key == b"origin" else value)
                for key, value in scope["headers"]
            ]}
        await self.app(scope, receive, send)