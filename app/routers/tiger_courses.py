"""Serve the course catalog search as JSON."""

from fastapi import APIRouter

import tiger_catalog

router: APIRouter = APIRouter()
router.add_api_route(
    "/courses",
    tiger_catalog.search_courses,
    methods=["GET"],
    tags=["Course Catalog"],
)
