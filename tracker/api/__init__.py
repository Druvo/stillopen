"""The JSON API behind the new app (`/api/v1/`).

A thin layer over the same services the HTML pages use; business rules stay in `services/`.

Rules that must hold (see docs/design/nextjs-frontend.md, section 4):
- one router-level dependency authenticates by session and CSRF; no route is public, and a signed-out call answers 401 JSON;
- every query is scoped to `request.user`; a row that is not the person's answers 404;
- no secrets in any response.
`tracker/tests_api.py` walks the OpenAPI schema, so a new route cannot skip the isolation checks."""
from .routes import api

__all__ = ["api"]
