from fastapi import APIRouter
from app.models.schemas import MetricsResponse
from app.services import session

router = APIRouter(tags=["Metrics"])

@router.get("/metrics", response_model=MetricsResponse)
def get_metrics():
    # Return the dynamic metrics stored in memory
    return session.current_metrics
