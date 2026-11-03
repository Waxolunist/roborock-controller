from dataclasses import asdict

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from roborock.exceptions import RoborockException

from roborock_controller.vacuum import NotPossible, UnknownRoutine, Vacuum

VACUUM = web.AppKey("vacuum", Vacuum)


def api_app(vacuum: Vacuum, health_max_age: float) -> web.Application:
    app = web.Application(middlewares=[_roborock_errors])
    app[VACUUM] = vacuum
    routes = web.RouteTableDef()

    @routes.get("/health")
    async def health(request: web.Request) -> web.Response:
        healthy = vacuum.fresh(health_max_age)
        return web.json_response({"healthy": healthy}, status=200 if healthy else 503)

    @routes.get("/status")
    async def status(request: web.Request) -> web.Response:
        return web.json_response(vacuum.status())

    @routes.get("/routines")
    async def routines(request: web.Request) -> web.Response:
        return web.json_response([asdict(routine) for routine in await vacuum.routines()])

    @routes.post("/routines/{routine_id:\\d+}")
    async def run_routine(request: web.Request) -> web.Response:
        try:
            routine = await vacuum.run_routine(int(request.match_info["routine_id"]))
        except UnknownRoutine:
            return web.json_response({"error": "unknown routine"}, status=404)
        return web.json_response({"started": asdict(routine)})

    @routes.post("/stop")
    async def stop(request: web.Request) -> web.Response:
        await vacuum.stop()
        return web.json_response({"sent": "stop"})

    @routes.post("/dock")
    async def dock(request: web.Request) -> web.Response:
        await vacuum.dock()
        return web.json_response({"sent": "dock"})

    @routes.post("/pause")
    async def pause(request: web.Request) -> web.Response:
        await vacuum.pause()
        return web.json_response({"sent": "pause"})

    @routes.post("/resume")
    async def resume(request: web.Request) -> web.Response:
        await vacuum.resume()
        return web.json_response({"sent": "resume"})

    app.add_routes(routes)
    return app


def metrics_app(vacuum: Vacuum) -> web.Application:
    app = web.Application()

    async def metrics(request: web.Request) -> web.Response:
        response = web.Response(body=generate_latest(vacuum.metrics.registry))
        response.content_type = CONTENT_TYPE_LATEST.split(";")[0]
        return response

    app.router.add_get("/metrics", metrics)
    return app


@web.middleware
async def _roborock_errors(request: web.Request, handler):
    try:
        return await handler(request)
    except NotPossible as e:
        return web.json_response({"error": str(e)}, status=409)
    except RoborockException as e:
        return web.json_response({"error": str(e) or type(e).__name__}, status=502)
