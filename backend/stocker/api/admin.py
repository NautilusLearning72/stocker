"""
Admin API Router.

Provides endpoints for managing strategy configuration.
"""

from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from stocker.services.config_service import config_service, TRADING_PARAMS

router = APIRouter()


# ---------- Pydantic Schemas ----------

class ConfigResponse(BaseModel):
    """Response schema for configuration entries."""
    key: str
    value: str
    value_type: str
    category: str
    description: Optional[str]

    class Config:
        from_attributes = True


class ConfigUpdate(BaseModel):
    """Request schema for updating a single config value."""
    value: str


class BulkConfigUpdate(BaseModel):
    """Request schema for updating multiple config values."""
    updates: Dict[str, str]


class ConfigMetadata(BaseModel):
    """Metadata about a config parameter for UI rendering."""
    key: str
    value_type: str
    category: str
    description: str
    tooltip: Optional[str] = None
    min: Optional[float] = None
    max: Optional[float] = None
    options: Optional[List[str]] = None


# ---------- Endpoints ----------

@router.get("/config", response_model=List[ConfigResponse])
async def list_config():
    """Get all configuration entries."""
    configs = await config_service.get_all()
    return configs


@router.get("/config/categories", response_model=List[str])
async def list_categories():
    """Get list of configuration categories."""
    categories = await config_service.get_categories()
    return categories


@router.get("/config/metadata", response_model=List[ConfigMetadata])
async def get_config_metadata():
    """Get metadata for all configuration parameters (for UI rendering)."""
    return [
        ConfigMetadata(
            key=key,
            value_type=meta["value_type"],
            category=meta["category"],
            description=meta["description"],
            tooltip=meta.get("tooltip"),
            min=meta.get("min"),
            max=meta.get("max"),
            options=meta.get("options"),
        )
        for key, meta in TRADING_PARAMS.items()
    ]


@router.get("/config/category/{category}", response_model=List[ConfigResponse])
async def get_config_by_category(category: str):
    """Get configuration entries for a specific category."""
    configs = await config_service.get_by_category(category)
    if not configs:
        raise HTTPException(status_code=404, detail=f"No configs found for category: {category}")
    return configs


@router.get("/config/{key}", response_model=ConfigResponse)
async def get_config(key: str):
    """Get a single configuration entry by key."""
    config = await config_service.get(key)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Config not found: {key}")
    return config


@router.put("/config/{key}", response_model=ConfigResponse)
async def update_config(key: str, body: ConfigUpdate):
    """
    Update a single configuration value.

    Note: Changes take effect after application restart.
    """
    try:
        config = await config_service.update(key, body.value)
        if config is None:
            raise HTTPException(status_code=404, detail=f"Config not found: {key}")
        return config
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/config", response_model=List[ConfigResponse])
async def bulk_update_config(body: BulkConfigUpdate):
    """
    Update multiple configuration values at once.

    Note: Changes take effect after application restart.
    """
    if not body.updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    try:
        configs = await config_service.bulk_update(body.updates)
        return configs
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
