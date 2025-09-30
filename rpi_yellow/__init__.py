import logging
import sys
from asyncio import sleep
from contextlib import asynccontextmanager
from functools import partial
import warnings

import aiosqlite
from gpiozero import LED, devices
import structlog
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request

from .settings import Settings, get_settings

warnings.filterwarnings("ignore", category=devices.PinFactoryFallback)

logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=logging.INFO,
)

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

PERMISSION_MAP = {"yellow": 17}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    app.state.triggered = set()

    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute(
            r"""
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                key TEXT NOT NULL,
                permissions TEXT NOT NULL
            )
            """
        )
        await db.commit()

    yield


class Actuator:
    def __init__(self, gpio_id):
        self.target = None
        self.gpio_id = gpio_id

        try:
            self.target = LED(gpio_id)
        except ImportError:
            pass

    def __getattr__(self, key):
        if self.target:
            return getattr(self.target, key)
        return partial(self._call_logger, method=key)

    def _call_logger(self, method, **kwargs):
        logger.info(gpio_id=self.gpio_id, method=method, **kwargs)


app = FastAPI(lifespan=lifespan)


async def _trigger(
    app: FastAPI,
    permission: str,
    settings,
):
    app.state.triggered.add(permission)
    try:
        app.state.triggered.add(permission)
        gpio_id = PERMISSION_MAP[permission]

        actuator = Actuator(gpio_id)
        actuator.on()
        await sleep(settings.trigger_time)
        actuator.off()
        await sleep(settings.backoff_time)

    finally:
        app.state.triggered.remove(permission)


@app.post("/call/{api_key}/trigger/{permission}")
async def trigger(
    request: Request,
    api_key: str,
    permission: str,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
):
    app = request.app

    async with aiosqlite.connect(settings.database_path) as db:
        async with db.execute(
            "SELECT name, permissions FROM api_keys WHERE key = ?", (api_key,)
        ) as cursor:
            if not (row := await cursor.fetchone()):
                raise HTTPException(status_code=403, detail="Permission denied")
        name, permissions = row

    if permission not in permissions:
        raise HTTPException(status_code=403, detail="Permission denied")

    if permission not in PERMISSION_MAP:
        raise HTTPException(status_code=501, detail="Trait not implemetned")

    status = "ok"

    if permission in app.state.triggered:
        status = "bounce"
    else:
        background_tasks.add_task(_trigger, app, permission, settings)

    logger.info("trigger", name=name, permission=permission, status=status)
    return {"detail": status}
