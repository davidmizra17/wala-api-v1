from datetime import timedelta

from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from conversations.models import Conversation, Message
from crm.models import Deal

# Spanish weekday abbreviations indexed by Python's weekday() (0=Monday)
_WEEKDAYS_ES = ["L", "M", "M", "J", "V", "S", "D"]

_ACTIVE_STAGES = [Deal.Stage.NEW, Deal.Stage.CONTACTED, Deal.Stage.QUALIFIED]

_FUNNEL_STAGES = [Deal.Stage.NEW, Deal.Stage.CONTACTED, Deal.Stage.QUALIFIED, Deal.Stage.WON]

_STAGE_LABELS = {
    Deal.Stage.NEW:       "Nuevo",
    Deal.Stage.CONTACTED: "Contactado",
    Deal.Stage.QUALIFIED: "Propuesta",
    Deal.Stage.WON:       "Ganado",
}


def _pct_change(current, previous):
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def _avg_response_seconds(conversations):
    """
    Average seconds from first inbound to first outbound message across
    a list/queryset of Conversation objects with messages prefetched.
    """
    diffs = []
    for conv in conversations:
        msgs = sorted(conv.messages.all(), key=lambda m: m.created)
        first_in = next((m for m in msgs if m.direction == Message.Direction.INBOUND), None)
        first_out = next((m for m in msgs if m.direction == Message.Direction.OUTBOUND), None)
        if first_in and first_out and first_out.created > first_in.created:
            diffs.append((first_out.created - first_in.created).total_seconds())
    return round(sum(diffs) / len(diffs)) if diffs else None


def _daily_counts(qs, since, date_field="created"):
    rows = (
        qs.filter(**{f"{date_field}__gte": since})
        .annotate(_date=TruncDate(date_field))
        .values("_date")
        .annotate(n=Count("id"))
        .order_by("_date")
    )
    return [row["n"] for row in rows]


class DashboardView(APIView):
    """
    GET /api/v1/reporting/dashboard/

    Query params:
        days        (int, default 7)  — KPI comparison window
        funnel_days (int, default 30) — Funnel look-back window
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        days = max(1, int(request.query_params.get("days", 7)))
        funnel_days = max(1, int(request.query_params.get("funnel_days", 30)))

        now = timezone.now()
        period_start = now - timedelta(days=days)
        prev_start = period_start - timedelta(days=days)
        sparkline_start = now - timedelta(days=14)
        funnel_start = now - timedelta(days=funnel_days)

        return Response(
            {
                "kpis": self._kpis(period_start, prev_start, sparkline_start),
                "message_volume": self._message_volume(sparkline_start),
                "activity": self._activity(now),
                "bot_resolution": self._bot_resolution(period_start),
                "by_channel": self._by_channel(period_start),
                "funnel": self._funnel(funnel_start, funnel_days),
            }
        )

    # -------------------------------------------------------------------------
    # KPIs
    # -------------------------------------------------------------------------

    def _kpis(self, period_start, prev_start, sparkline_start):
        # Conversations
        conv_curr = Conversation.objects.filter(created__gte=period_start).count()
        conv_prev = Conversation.objects.filter(
            created__gte=prev_start, created__lt=period_start
        ).count()

        # Active deals — current snapshot count; change rate based on new deals in period
        active_now = Deal.objects.filter(stage__in=_ACTIVE_STAGES).count()
        new_active_curr = Deal.objects.filter(
            stage__in=_ACTIVE_STAGES, created__gte=period_start
        ).count()
        new_active_prev = Deal.objects.filter(
            stage__in=_ACTIVE_STAGES,
            created__gte=prev_start,
            created__lt=period_start,
        ).count()

        # Avg response time — computed in Python after prefetching messages
        curr_convos = list(
            Conversation.objects.filter(created__gte=period_start).prefetch_related("messages")
        )
        prev_convos = list(
            Conversation.objects.filter(
                created__gte=prev_start, created__lt=period_start
            ).prefetch_related("messages")
        )
        resp_curr = _avg_response_seconds(curr_convos)
        resp_prev = _avg_response_seconds(prev_convos)
        resp_change = _pct_change(resp_curr, resp_prev) if resp_curr is not None else None

        # Conversion rate
        total_curr = Deal.objects.filter(created__gte=period_start).count()
        won_curr = Deal.objects.filter(
            created__gte=period_start, stage=Deal.Stage.WON
        ).count()
        total_prev = Deal.objects.filter(
            created__gte=prev_start, created__lt=period_start
        ).count()
        won_prev = Deal.objects.filter(
            created__gte=prev_start, created__lt=period_start, stage=Deal.Stage.WON
        ).count()
        rate_curr = round(won_curr / total_curr * 100, 1) if total_curr else 0.0
        rate_prev = round(won_prev / total_prev * 100, 1) if total_prev else 0.0

        return {
            "conversations": {
                "value": conv_curr,
                "change_pct": _pct_change(conv_curr, conv_prev),
                "sparkline": _daily_counts(Conversation.objects.all(), sparkline_start),
            },
            "active_deals": {
                "value": active_now,
                "change_pct": _pct_change(new_active_curr, new_active_prev),
                "sparkline": _daily_counts(
                    Deal.objects.filter(stage__in=_ACTIVE_STAGES), sparkline_start
                ),
            },
            "avg_response_time_secs": {
                "value": resp_curr,
                "change_pct": resp_change,
                "sparkline": [],
            },
            "conversion_rate_pct": {
                "value": rate_curr,
                "change_pct": _pct_change(rate_curr, rate_prev),
                "sparkline": [],
            },
        }

    # -------------------------------------------------------------------------
    # Message volume (last 14 days, bot vs human per day)
    # -------------------------------------------------------------------------

    def _message_volume(self, since):
        rows = (
            Message.objects.filter(created__gte=since)
            .annotate(date=TruncDate("created"))
            .values("date")
            .annotate(
                bot=Count("id", filter=Q(sender_type=Message.SenderType.BOT)),
                human=Count("id", filter=~Q(sender_type=Message.SenderType.BOT)),
            )
            .order_by("date")
        )
        return [
            {
                "date": row["date"].isoformat(),
                "weekday": _WEEKDAYS_ES[row["date"].weekday()],
                "bot": row["bot"],
                "human": row["human"],
            }
            for row in rows
        ]

    # -------------------------------------------------------------------------
    # Live activity feed (10 most recently updated conversations)
    # -------------------------------------------------------------------------

    def _activity(self, now):
        recent = (
            Conversation.objects.select_related("contact", "channel")
            .prefetch_related("messages")
            .order_by("-modified")[:10]
        )
        result = []
        for conv in recent:
            msgs = sorted(conv.messages.all(), key=lambda m: m.created, reverse=True)
            last_msg = msgs[0] if msgs else None
            elapsed = now - conv.modified
            minutes_ago = int(elapsed.total_seconds() / 60)
            result.append(
                {
                    "conversation_id": str(conv.id),
                    "contact_name": conv.contact.name if conv.contact else None,
                    "channel": conv.channel.platform if conv.channel else None,
                    "status": conv.status,
                    "last_message": last_msg.text if last_msg else None,
                    "minutes_ago": minutes_ago,
                }
            )
        return result

    # -------------------------------------------------------------------------
    # Bot resolution (all conversations in period split by human involvement)
    # -------------------------------------------------------------------------

    def _bot_resolution(self, since):
        human_sent = Message.objects.filter(
            conversation=OuterRef("pk"),
            sender_type=Message.SenderType.HUMAN,
        )
        convos = Conversation.objects.filter(created__gte=since)
        bot_count = convos.filter(~Exists(human_sent)).count()
        human_count = convos.filter(Exists(human_sent)).count()
        total = bot_count + human_count
        bot_pct = round(bot_count / total * 100, 1) if total else 0.0

        avg_resp = _avg_response_seconds(
            convos.prefetch_related("messages")
        )

        return {
            "bot_count": bot_count,
            "human_count": human_count,
            "bot_pct": bot_pct,
            "avg_first_response_secs": avg_resp,
        }

    # -------------------------------------------------------------------------
    # By channel (conversation count per platform in period)
    # -------------------------------------------------------------------------

    def _by_channel(self, since):
        rows = (
            Conversation.objects.filter(created__gte=since, channel__isnull=False)
            .values("channel__platform")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        total = sum(r["count"] for r in rows)
        return [
            {
                "channel": row["channel__platform"],
                "count": row["count"],
                "pct": round(row["count"] / total * 100, 1) if total else 0.0,
            }
            for row in rows
        ]

    # -------------------------------------------------------------------------
    # Deal funnel (count + value per stage in period)
    # -------------------------------------------------------------------------

    def _funnel(self, since, funnel_days):
        rows = (
            Deal.objects.filter(created__gte=since, stage__in=_FUNNEL_STAGES)
            .values("stage")
            .annotate(count=Count("id"), total_value=Sum("value"))
        )
        by_stage = {r["stage"]: r for r in rows}
        stages = []
        for stage in _FUNNEL_STAGES:
            data = by_stage.get(stage, {"count": 0, "total_value": None})
            stages.append(
                {
                    "stage": stage,
                    "label": _STAGE_LABELS[stage],
                    "count": data["count"],
                    "value": float(data["total_value"] or 0),
                }
            )
        total_value = sum(s["value"] for s in stages)
        return {
            "days": funnel_days,
            "total_value": total_value,
            "stages": stages,
        }
