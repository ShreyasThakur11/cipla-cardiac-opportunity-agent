"""FastAPI application.

Two groups of endpoints. ``/agent/*`` runs the full reasoning loop, which costs
model tokens and takes seconds. ``/analytics/*`` returns the deterministic
analysis directly, which costs nothing and returns in milliseconds - use those
when you know exactly what you want and do not need it narrated.

The heavy objects (warehouse, scorecard, retrieval index) are built once during
startup rather than per request. A cold first request would otherwise take
several seconds and make the service look broken.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..analytics.competition import top_competitors
from ..analytics.forecast import forecast_space
from ..analytics.sensitivity import run_sensitivity
from ..analytics.whitespace import find_whitespace
from ..config import get_settings
from ..logging_config import configure_logging, get_logger
from ..pipeline import AnalysisContext, WarehouseMissingError, get_context
from .schemas import (
    AskRequest,
    AskResponse,
    ForecastRequest,
    HealthResponse,
    RankRequest,
    SensitivityRequest,
    SignalSearchRequest,
)

logger = get_logger(__name__)

#: Populated at startup so no request pays the build cost.
_state: dict[str, Any] = {"context": None, "agent": None, "error": None}


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """Build the analysis context and agent once, at startup."""
    configure_logging()
    try:
        from ..agent import build_agent

        context = get_context()
        _state["context"] = context
        _state["agent"] = build_agent(context)
        logger.info("api.startup", spaces=len(context.scored), signals=len(context.corpus))
    except WarehouseMissingError as exc:
        # Start anyway so /health can explain what is wrong, rather than
        # failing to boot with a stack trace in the console.
        _state["error"] = str(exc)
        logger.error("api.startup.warehouse_missing", error=str(exc))
    except Exception as exc:  # noqa: BLE001
        _state["error"] = f"{type(exc).__name__}: {exc}"
        logger.error("api.startup.failed", error=str(exc), exc_info=True)
    yield
    _state.clear()


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Optional shared-secret check, enabled by setting ``CARDIAC_API_KEY``."""
    expected = get_settings().api_key
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-API-Key header.",
        )


def get_analysis_context() -> AnalysisContext:
    context = _state.get("context")
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_state.get("error")
            or "The analysis context is not ready. Run `cardiac-agent build` and restart.",
        )
    return context


def create_app() -> FastAPI:
    """Build the application. Separated from the module-level instance for tests."""
    settings = get_settings()
    app = FastAPI(
        title="Cardiac Opportunity Agent",
        description=(
            "Prioritises opportunity spaces in the India Cardiac market where Cipla has a "
            "sustainable right to win. Every figure is computed deterministically; the "
            "language model narrates, it does not calculate."
        ),
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # ---------------------------------------------------------------- health

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        """Liveness and readiness, with enough detail to diagnose a bad start."""
        settings = get_settings()
        context = _state.get("context")
        if context is None:
            return HealthResponse(
                status="degraded",
                version=__version__,
                warehouse_built=False,
                spaces_scored=0,
                signals_loaded=0,
                llm_provider=settings.llm_provider,
                llm_available=settings.llm_available,
                detail=_state.get("error") or "Analysis context not built.",
            )
        return HealthResponse(
            status="ok",
            version=__version__,
            warehouse_built=True,
            spaces_scored=len(context.scored),
            signals_loaded=len(context.corpus),
            llm_provider=settings.llm_provider,
            llm_available=settings.llm_available,
            market_value_cr=round(context.totals["market_value_t2"], 1),
            as_of=context.as_of,
        )

    # ----------------------------------------------------------------- agent

    @app.post(
        "/agent/ask",
        response_model=AskResponse,
        tags=["agent"],
        dependencies=[Depends(require_api_key)],
    )
    def ask(request: AskRequest) -> AskResponse:
        """Answer a question with the full reasoning loop."""
        agent = _state.get("agent")
        if agent is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_state.get("error") or "The agent is not ready.",
            )
        result = agent.ask(request.question)
        return AskResponse(
            answer=result.answer,
            citations=result.citations,
            tools_used=result.state.tools_used,
            deterministic=result.state.deterministic,
            warnings=result.state.warnings,
            trace=result.state.to_trace() if request.include_trace else None,
            evidence=result.evidence if request.include_evidence else None,
        )

    # ------------------------------------------------------------- analytics

    @app.get("/analytics/overview", tags=["analytics"])
    def overview(context: AnalysisContext = Depends(get_analysis_context)) -> dict[str, Any]:
        """Market totals and the focal company's standing."""
        from ..agent.tools import market_overview

        return market_overview(context)

    @app.post("/analytics/rank", tags=["analytics"])
    def rank(
        request: RankRequest, context: AnalysisContext = Depends(get_analysis_context)
    ) -> dict[str, Any]:
        """Ranked scorecard at one space level."""
        from ..agent.tools import ToolError, rank_opportunity_spaces

        try:
            return rank_opportunity_spaces(
                context,
                level=request.level,
                top_n=request.top_n,
                rank_by=request.rank_by,
                min_value_cr=request.min_value_cr,
            )
        except ToolError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/analytics/space/{space_id}", tags=["analytics"])
    def space(
        space_id: str, context: AnalysisContext = Depends(get_analysis_context)
    ) -> dict[str, Any]:
        """Full evidence card for one space."""
        from ..agent.tools import ToolError, space_deep_dive

        try:
            return space_deep_dive(context, space=space_id)
        except ToolError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/analytics/whitespace", tags=["analytics"])
    def whitespace(
        limit: int = 10, context: AnalysisContext = Depends(get_analysis_context)
    ) -> dict[str, Any]:
        """Underpenetrated spaces with a credible route in."""
        result = find_whitespace(
            context.scored,
            focal_overall_share=context.totals["focal_share"],
            levels=["sub_segment", "molecule_combination", "anchor_molecule"],
            limit=limit,
        )
        return {
            "count": int(len(result)),
            "fair_share_benchmark_pct": round(context.totals["focal_share"] * 100.0, 2),
            "spaces": result.to_dict(orient="records"),
        }

    @app.post("/analytics/forecast", tags=["analytics"])
    def forecast(
        request: ForecastRequest, context: AnalysisContext = Depends(get_analysis_context)
    ) -> dict[str, Any]:
        """Project one space forward, with a scenario band."""
        row = context.find_space(request.space, request.level)
        if row is None:
            raise HTTPException(status_code=404, detail=f"No space matches '{request.space}'.")
        result = forecast_space(
            row,
            market_cagr=context.totals["market_cagr_2y"],
            framework=context.framework,
            horizon_years=request.horizon_years,
        )
        return result.to_dict()

    @app.post("/analytics/sensitivity", tags=["analytics"])
    def sensitivity(
        request: SensitivityRequest, context: AnalysisContext = Depends(get_analysis_context)
    ) -> dict[str, Any]:
        """Rank stability under randomised framework weights."""
        result = run_sensitivity(
            context.enriched,
            level=request.level,
            framework=context.framework,
            iterations=request.iterations,
            top_k=request.top_k,
        )
        return {
            "level": request.level,
            "iterations": result.iterations,
            "top_k": result.top_k,
            "stability": result.stability.to_dict(orient="records"),
        }

    @app.get("/analytics/competitor/{company}", tags=["analytics"])
    def competitor(
        company: str, context: AnalysisContext = Depends(get_analysis_context)
    ) -> dict[str, Any]:
        """Profile of one competitor in the Cardiac market."""
        from ..agent.tools import ToolError, competitor_profile

        try:
            return competitor_profile(context, company=company)
        except ToolError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/analytics/space/{space_id}/competitors", tags=["analytics"])
    def space_competitors(
        space_id: str,
        level: str = "molecule_combination",
        context: AnalysisContext = Depends(get_analysis_context),
    ) -> dict[str, Any]:
        """Leading players inside one space."""
        frame = top_competitors(context.company_facts, level, space_id, limit=10)
        if frame.empty:
            raise HTTPException(status_code=404, detail=f"No competitors found for '{space_id}'.")
        return {"space_id": space_id, "level": level, "companies": frame.to_dict(orient="records")}

    # --------------------------------------------------------------- signals

    @app.post("/signals/search", tags=["signals"])
    def search_signals(
        request: SignalSearchRequest, context: AnalysisContext = Depends(get_analysis_context)
    ) -> dict[str, Any]:
        """Search the external-signal corpus."""
        passages = context.retriever.search(request.query, top_k=request.top_k)
        return {"query": request.query, "hits": [passage.to_dict() for passage in passages]}

    @app.get("/signals/citations", tags=["signals"])
    def citations(context: AnalysisContext = Depends(get_analysis_context)) -> dict[str, Any]:
        """Every source in the corpus, formatted for the appendix."""
        return {"count": len(context.corpus), "citations": context.citations()}

    return app


app = create_app()

__all__ = ["app", "create_app", "get_analysis_context", "require_api_key"]
