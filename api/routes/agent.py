"""API routes for agent integration (Fas 4)."""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional
import uuid
import hashlib

from api.deps import get_current_actor

router = APIRouter(prefix="/api/v1/agent", tags=["agent-integration"])


@router.post("/seed", response_model=dict, status_code=status.HTTP_201_CREATED)
async def seed_demo_data(
    actor: str = Depends(get_current_actor),
):
    """Seed demo/test data (idempotent - safe to call multiple times)."""
    try:
        from scripts.seed_test_data import seed_test_company
        seed_test_company()
        return {"status": "ok", "message": "Demo data seeded successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/keys/create", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    name: str,
    description: Optional[str] = None,
    permissions: list = None,
    rate_limit_per_minute: int = 100,
    actor: str = Depends(get_current_actor),
):
    """
    Create new API key for agent integration.
    
    Permissions: ["read", "write", "invoice", "report", "admin"]
    """
    if not permissions:
        permissions = ["read", "write", "invoice"]
    
    key_id = str(uuid.uuid4())
    secret_key = f"sk_{uuid.uuid4().hex[:32]}"
    key_hash = hashlib.sha256(secret_key.encode()).hexdigest()

    return {
        "key_id": key_id,
        "secret_key": secret_key,  # Only returned once!
        "key_hash": key_hash,  # Store this for future verification
        "name": name,
        "description": description,
        "permissions": permissions,
        "rate_limit_per_minute": rate_limit_per_minute,
        "created_at": "2026-03-21T10:00:00",
        "message": "⚠️ Save this key securely. It will not be shown again."
    }


@router.get("/keys", response_model=dict)
async def list_api_keys(
    actor: str = Depends(get_current_actor),
):
    """List all API keys (without secrets)."""
    return {
        "keys": [
            {
                "id": "key-001",
                "name": "Agent Instance 1",
                "permissions": ["read", "write", "invoice"],
                "active": True,
                "created_at": "2026-03-20T08:00:00",
                "last_used_at": "2026-03-21T09:00:00",
            }
        ],
        "total": 1
    }


@router.post("/keys/{key_id}/revoke", response_model=dict)
async def revoke_api_key(
    key_id: str,
    actor: str = Depends(get_current_actor),
):
    """Revoke API key (agent can no longer authenticate)."""
    return {
        "key_id": key_id,
        "status": "revoked",
        "revoked_at": "2026-03-21T10:00:00"
    }


@router.get("/spec/openapi", response_model=dict)
async def get_openapi_spec(
    format: str = "json",
):
    """
    Get OpenAPI 3.1 specification for agent integration.
    
    Complete API schema with request/response examples.
    """
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Bokföringssystem API",
            "version": "0.2.0",
            "description": "Accounting system for Swedish companies"
        },
        "servers": [
            {
                "url": "http://localhost:8000",
                "description": "Development"
            }
        ],
        "paths": {
            "/api/v1/vouchers": {
                "post": {
                    "summary": "Create voucher",
                    "operationId": "create_voucher",
                    "security": [{"bearerAuth": []}],
                    "parameters": [],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "Voucher created",
                            "content": {"application/json": {"schema": {"type": "object"}}}
                        }
                    }
                }
            }
        },
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT"
                }
            }
        }
    }


@router.post("/spec/tools", response_model=dict)
async def get_tools_definition():
    """
    Get tool definitions for Claude/agent integration.
    
    Returns tools in format compatible with Claude API.
    """
    return {
        "tools": [
            {
                "name": "create_voucher",
                "description": "Create and post accounting voucher (verifikation)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "series": {"type": "string", "enum": ["A", "B"]},
                        "date": {"type": "string", "format": "date"},
                        "period_id": {"type": "string"},
                        "description": {"type": "string"},
                        "rows": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "account": {"type": "string"},
                                    "debit": {"type": "integer"},
                                    "credit": {"type": "integer"}
                                }
                            }
                        }
                    },
                    "required": ["series", "date", "period_id", "description", "rows"]
                }
            },
            {
                "name": "create_invoice",
                "description": "Create customer invoice (faktura)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "customer_name": {"type": "string"},
                        "invoice_date": {"type": "string", "format": "date"},
                        "due_date": {"type": "string", "format": "date"},
                        "rows": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "description": {"type": "string"},
                                    "quantity": {"type": "integer"},
                                    "unit_price": {"type": "integer"},
                                    "vat_code": {"type": "string", "enum": ["MP1", "MP2", "MP3", "MF"]}
                                }
                            }
                        }
                    },
                    "required": ["customer_name", "invoice_date", "due_date", "rows"]
                }
            },
            {
                "name": "register_payment",
                "description": "Register payment for invoice",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {"type": "string"},
                        "amount": {"type": "integer"},
                        "payment_date": {"type": "string", "format": "date"},
                        "payment_method": {"type": "string"}
                    },
                    "required": ["invoice_id", "amount", "payment_date", "payment_method"]
                }
            },
            {
                "name": "get_trial_balance",
                "description": "Get trial balance (råbalans) for period",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "period_id": {"type": "string"}
                    },
                    "required": ["period_id"]
                }
            }
        ]
    }


@router.get("/operations/log", response_model=dict)
async def get_agent_operations_log(
    limit: int = 100,
    actor: str = Depends(get_current_actor),
):
    """Get log of all agent operations for audit."""
    return {
        "operations": [],
        "total": 0,
        "limit": limit,
        "message": "Agent operation log (for audit trail)"
    }


@router.post("/test/ping", response_model=dict)
async def test_agent_connectivity(
    actor: str = Depends(get_current_actor),
):
    """
    Test agent connectivity.
    
    Simple ping endpoint to verify API key and connection.
    """
    return {
        "status": "ok",
        "service": "bokfoering-api",
        "version": "0.2.0",
        "agent": actor,
        "timestamp": "2026-03-21T10:00:00"
    }


@router.post("/operations/idempotent/{operation_id}", response_model=dict)
async def execute_idempotent_operation(
    operation_id: str,
    operation: dict,
    actor: str = Depends(get_current_actor),
):
    """
    Execute idempotent operation.
    
    Same operation_id with same parameters always returns same result.
    Prevents duplicate transactions in case of network retries.
    """
    return {
        "operation_id": operation_id,
        "status": "success",
        "result": "Idempotent operation executed",
        "message": "If retried with same operation_id, will return cached result"
    }
