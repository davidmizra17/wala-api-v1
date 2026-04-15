from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Deal, Order, Pipeline, Task
from .serializers import (
    BoardSerializer,
    DealSerializer,
    OrderSerializer,
    PipelineSerializer,
    TaskSerializer,
)


class PipelineViewSet(viewsets.ModelViewSet):
    serializer_class = PipelineSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Pipeline.objects.all().order_by("created")


class DealViewSet(viewsets.ModelViewSet):
    serializer_class = DealSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Deal.objects.select_related("contact", "pipeline")
            .prefetch_related("tasks")
            .order_by("-created")
        )


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Task.objects.select_related("deal", "assigned_to").order_by("due_date", "created")
        deal_id = self.request.query_params.get("deal")
        if deal_id:
            qs = qs.filter(deal_id=deal_id)
        return qs


class BoardView(APIView):
    """
    GET /api/v1/crm/board/

    Returns all deals for the tenant's default pipeline grouped by stage.
    The frontend uses this to render the Kanban board.

    One query: all deals for the pipeline, grouped in Python — no N+1.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        pipeline = Pipeline.objects.order_by("created").first()

        if pipeline is None:
            return Response({"detail": "No pipeline configured for this tenant."}, status=404)

        deals = (
            Deal.objects.filter(pipeline=pipeline)
            .select_related("contact")
            .prefetch_related("tasks")
            .order_by("-created")
        )

        # Group in Python — avoids N+1 and keeps the query simple
        deals_by_stage = {}
        for deal in deals:
            deals_by_stage.setdefault(deal.stage, []).append(deal)

        columns = [
            {
                "stage": stage.value,
                "label": stage.label,
                "deals": deals_by_stage.get(stage.value, []),
            }
            for stage in Deal.STAGE_ORDER
        ]

        data = BoardSerializer({"pipeline": pipeline, "columns": columns}).data
        return Response(data)


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.prefetch_related("items").order_by("-created")
