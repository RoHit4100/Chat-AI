"""ASGI config for config project with checkpointer lifespan lifecycle management."""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

async def application(scope, receive, send):
    """ASGI entrypoint supporting ASGI lifespan for checkpointer pool lifecycle."""
    if scope["type"] == "lifespan":
        from agent.checkpointer import checkpointer_manager
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    await checkpointer_manager.start()
                    await send({"type": "lifespan.startup.complete"})
                except Exception as exc:
                    await send({"type": "lifespan.startup.failed", "message": str(exc)})
            elif message["type"] == "lifespan.shutdown":
                try:
                    await checkpointer_manager.close()
                finally:
                    await send({"type": "lifespan.shutdown.complete"})
                return
    else:
        await django_asgi_app(scope, receive, send)
