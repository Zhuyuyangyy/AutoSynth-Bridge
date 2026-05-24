from fastapi import APIRouter, HTTPException
from typing import Optional

from providers.registry import ProviderRegistry

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


def _get_registry() -> ProviderRegistry:
    from providers.registry import get_registry
    registry = get_registry()
    if not registry.list_names():
        raise HTTPException(status_code=503, detail="ProviderRegistry not initialized or empty")
    return registry


@router.get("/health")
async def providers_health():
    registry = _get_registry()
    health_results = await registry.health_check_all()
    providers = []
    for name, health in health_results.items():
        providers.append(health.to_dict())
    return {"providers": providers, "total": len(providers)}


@router.get("/list")
async def providers_list():
    registry = _get_registry()
    names = registry.list_names()
    available = registry.get_available_providers()
    return {
        "providers": [
            {"name": name, "enabled": available.get(name) is not None}
            for name in names
        ],
        "total": len(names),
        "available": len(available),
    }


@router.get("/{provider_name}/health")
async def provider_health(provider_name: str):
    registry = _get_registry()
    if not registry.has(provider_name):
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
    provider = registry.get(provider_name)
    health = await provider.health_check()
    return health.to_dict()


@router.get("/fallback/status")
async def fallback_status():
    from providers.fallback_chain import FallbackChain
    registry = _get_registry()
    chains = {}
    for name in registry.list_names():
        provider = registry.get(name)
        if isinstance(provider, FallbackChain):
            chain = provider.get_chain()
            chains[name] = {
                "type": "fallback_chain",
                "providers": [
                    {"name": p.name, "type": getattr(p, "provider_type", "unknown"), "enabled": p.enabled}
                    for p in chain
                ],
                "total": len(chain),
                "enabled": sum(1 for p in chain if p.enabled),
            }
    return {"fallback_chains": chains, "total": len(chains)}
