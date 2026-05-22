"""DEPRECATED — routes split into routes_query.py, routes_upload.py, routes_notebook.py.

This file is kept empty to avoid import errors from any cached references.
Remove after confirming no external code imports from app.api.routes.
"""
from fastapi import APIRouter
router = APIRouter()  # empty — all routes are in the three new files
