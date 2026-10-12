"""HTTP API v1, one router module per area. ``router`` is mounted by ``app.main`` at ``/api/v1`` (and at the
root for MAVE <= 0.2 clients). Business logic stays in the service modules (``app.auth``, ``app.admin``,
``app.search``, ``app.ai``); these modules only translate HTTP <-> service calls."""
from fastapi import APIRouter

from . import admin, ai, auth, health, history, saved, search, trending, users

router = APIRouter()
for _module in (auth, search, trending, ai, users, history, saved, admin, health):
    router.include_router(_module.router)
