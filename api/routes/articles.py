"""API routes for article register."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps import get_current_actor
from domain.invoice_validation import ValidationError
from services.customer_article import ArticleService

router = APIRouter(prefix="/api/v1/articles", tags=["articles"])


class CreateArticleRequest(BaseModel):
    article_number: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    unit: str = "st"
    unit_price: int = Field(0, ge=0, description="Unit price in öre")
    vat_code: str = Field("MP1", pattern="^(MP1|MP2|MP3|MF)$")
    revenue_account: str = "3010"


@router.get("", response_model=dict)
async def list_articles(
    active_only: bool = Query(True),
    search: Optional[str] = Query(None),
):
    service = ArticleService()
    articles = service.list_articles(active_only=active_only, search=search)
    return {"articles": [_article_to_dict(article) for article in articles]}


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_article(
    request: CreateArticleRequest,
    actor: str = Depends(get_current_actor),
):
    try:
        article = ArticleService().create_article(**request.model_dump())
        return _article_to_dict(article)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "error": exc.message})


def _article_to_dict(article) -> dict:
    return {
        "id": article.id,
        "article_number": article.article_number,
        "name": article.name,
        "description": article.description,
        "unit": article.unit,
        "unit_price": article.unit_price,
        "vat_code": article.vat_code,
        "revenue_account": article.revenue_account,
        "active": article.active,
        "created_at": article.created_at,
        "updated_at": article.updated_at,
    }
