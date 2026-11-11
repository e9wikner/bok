"""Bokslutet per räkenskapsår: översikt, uppgifter och nedladdningar.

GET  /api/v1/bokslut/{fy}                 översikt med kontroller
GET  /api/v1/bokslut/{fy}/uppgifter       uppgifter och historik
POST /api/v1/bokslut/{fy}/uppgifter       {"values": {nyckel: värde | null}}
GET  /api/v1/bokslut/{fy}/filer/{namn}    INFO.SRU, BLANKETTER.SRU, sru.zip,
                                          moms.eskd, momsdeklaration.pdf,
                                          arsredovisning.pdf,
                                          faststallelseintyg.pdf
GET  /api/v1/bokslut/{fy}/arsredovisning.html   förhandsvisning
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from api.deps import Caller, get_caller
from domain.validation import ValidationError

router = APIRouter(prefix="/api/v1/bokslut", tags=["bokslut"])


class UppgifterIn(BaseModel):
    values: Dict[str, Any]


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{fiscal_year_id}")
async def get_bokslut(fiscal_year_id: str):
    from services.bokslut import BokslutService

    try:
        return BokslutService().overview(fiscal_year_id)
    except ValueError as exc:
        raise _not_found(exc)


@router.get("/{fiscal_year_id}/uppgifter")
async def get_uppgifter(fiscal_year_id: str):
    from services.bokslut_inputs import BokslutInputsService, schema

    service = BokslutInputsService()
    values, inherited = service.resolve(fiscal_year_id)
    return {
        "values": values,
        "inherited": inherited,
        "history": service.history(fiscal_year_id),
        "schema": schema(),
    }


@router.post("/{fiscal_year_id}/uppgifter")
async def post_uppgifter(
    fiscal_year_id: str, body: UppgifterIn, caller: Caller = Depends(get_caller)
):
    from services.bokslut_inputs import BokslutInputsService

    try:
        values = BokslutInputsService().set_values(
            fiscal_year_id, body.values, caller.actor
        )
    except ValidationError as exc:
        code = 404 if exc.code == "fiscal_year_not_found" else 422
        raise HTTPException(
            status_code=code,
            detail={
                "error": exc.message,
                "code": exc.code,
                "details": exc.details,
                **exc.payload,
            },
        )
    return {"values": values}


@router.get("/{fiscal_year_id}/filer/{name}")
async def get_fil(fiscal_year_id: str, name: str):
    from services.bokslut import BokslutService

    try:
        content, media_type, filename = BokslutService().file(fiscal_year_id, name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Okänd fil: {name}")
    except ValueError as exc:
        raise _not_found(exc)
    except RuntimeError as exc:  # WeasyPrint saknas
        raise HTTPException(status_code=500, detail=str(exc))
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{fiscal_year_id}/arsredovisning.html", response_class=HTMLResponse)
async def get_arsredovisning_html(fiscal_year_id: str):
    from services.arsredovisning import render_arsredovisning_html

    try:
        return render_arsredovisning_html(fiscal_year_id)
    except ValueError as exc:
        raise _not_found(exc)
