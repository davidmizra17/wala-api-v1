from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BoardView, DealViewSet, OrderViewSet, PipelineViewSet, TaskViewSet

router = DefaultRouter()
router.register("pipelines", PipelineViewSet, basename="pipeline")
router.register("deals", DealViewSet, basename="deal")
router.register("tasks", TaskViewSet, basename="task")
router.register("orders", OrderViewSet, basename="order")

urlpatterns = [
    path("board/", BoardView.as_view(), name="crm-board"),
] + router.urls
