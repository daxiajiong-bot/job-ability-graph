"""FastAPI dependencies for the API edge."""

from __future__ import annotations

from fastapi import Request

from backend.app.application.use_cases.contract_facade import ContractFacade


def get_facade(request: Request) -> ContractFacade:
    return request.app.state.container.facade
