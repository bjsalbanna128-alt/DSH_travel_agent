import re
from copy import deepcopy
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import exists, func, or_, select

from app.db.models import Trip, TripVersion
from app.db.scenic_models import PlanningQualityReport, PlanningQualityRule
from app.db.support_models import utc_now
from app.schemas.admin_resources import ResourcePage
from app.schemas.scenic_quality import QualityDetail, QualityFinding, QualitySummary
from app.services.scenic_restrictions import city_key, name_key

DATE_PATTERN = r"(?<![0-9])([0-9]{4})(?:[-/]|年)([0-9]{1,2})(?:[-/]|月)([0-9]{1,2})(?:日|号)?(?![0-9])"
NOTES_START = "\n\n【规划质检提示】\n"
RESTRICTION_LABELS = {"closure": "闭园", "reservation": "需预约", "admission": "入园限制"}


def dates_in_text(text):
    result = []
    for year, month, day in re.findall(DATE_PATTERN, text or ""):
        try:
            result.append(date(int(year), int(month), int(day)))
        except ValueError:
            continue
    return list(dict.fromkeys(result))


def explicit_departure(text):
    match = re.search(rf"{DATE_PATTERN}\s*(?:出发|启程|开始|至|到|—|~|～)", text or "")
    if match:
        dates = dates_in_text(match[0])
        if dates:
            return dates[0]
    dates = dates_in_text(text)
    if len(dates) != 1 or re.search(rf"{DATE_PATTERN}\s*(?:返程|返回|回程|离开|结束)", text or ""):
        return None
    return dates[0]


def trip_day(request, day):
    if type(day) is not int or day < 1:
        return None
    starts_on = explicit_departure(request.get("travel_time"))
    if starts_on is None:
        return None
    try:
        return starts_on + timedelta(days=day - 1)
    except OverflowError:
        return None


def _identity(item):
    return (item["source"], item["id"]) if item.get("source") in ("amap", "chroma", "content") and item.get("id") else None


def with_poi_identity(item, known):
    """Only copy source and city from a candidate that actually came from POI search."""
    clean = {key: value for key, value in item.items() if key not in ("source", "city")}
    item_id = clean.get("id")
    name = name_key(clean.get("name") or "")
    by_name = [candidate for candidate in known if name_key(candidate.get("name") or "") == name]
    if item_id:
        by_id = [candidate for candidate in by_name if candidate.get("id") == item_id]
        if by_id:
            by_name = by_id
        elif any(candidate.get("id") == item_id for candidate in known):
            return clean
    identities = {_identity(candidate): candidate for candidate in by_name if _identity(candidate)}
    if len(identities) == 1:
        identity, candidate = next(iter(identities.items()))
        clean.update(source=identity[0], id=identity[1], city=candidate.get("city") or "")
        # Carry the sellability we resolved for this place; the LLM never invents it.
        for extra in ("content_id", "offer"):
            if candidate.get(extra):
                clean[extra] = candidate[extra]
    return clean


def matches(item, destination, snapshot):
    if not snapshot.get("available"):
        return []
    city = city_key(item.get("city") or destination)
    name = name_key(item.get("name") or "")
    identity = _identity(item)
    eligible = [rule for rule in snapshot["rules"] if city_key(rule["poi"]["city"]) == city]
    exact = [rule for rule in eligible if identity and _identity(rule["poi"]) == identity]
    if exact:
        return [(rule, "id") for rule in exact]
    same_name = [rule for rule in eligible if name and name_key(rule["poi"]["name"]) == name]
    unique = {(_identity(rule["poi"])) for rule in same_name}
    unresolved = len(unique) != 1 or (
        item.get("id") and any(
            rule["poi"]["id"] != item["id"] and (
                identity is None or rule["poi"]["source"] == item["source"]
            ) for rule in same_name
        )
    )
    return [(rule, "ambiguous" if unresolved else "unique_name") for rule in same_name]


def _applies(rule, when):
    return rule["starts_on"] <= when.isoformat() and (rule["ends_on"] is None or when.isoformat() <= rule["ends_on"])


def available_days(item, request, snapshot):
    days = range(1, max(1, request.get("days", 1)) + 1)
    if trip_day(request, 1) is None:
        return days
    closures = [rule for rule, basis in matches(item, request.get("destination", ""), snapshot)
                if rule["kind"] == "closure" and basis != "ambiguous"]
    if not closures:
        return days
    allowed = []
    for day in days:
        when = trip_day(request, day)
        if when is None or all(not _applies(rule, when) for rule in closures):
            allowed.append(day)
    return allowed


def route_guidance(attractions, request, snapshot):
    summary = {}
    for item in attractions:
        identified = item.get("id") or item.get("name")
        allowed = available_days(item, request, snapshot)
        notices = []
        for rule, basis in matches(item, request.get("destination", ""), snapshot):
            if rule["kind"] == "closure" and basis != "ambiguous":
                continue
            for day in allowed:
                when = trip_day(request, day)
                if when is not None and _applies(rule, when):
                    notices.append({"day": day, "kind": rule["kind"], "needs_verification": basis == "ambiguous"})
        if not isinstance(allowed, range) or notices:
            summary[identified] = {"allowed_days": list(allowed), "notices": notices}
    return summary


def _scenic_findings(days, request, snapshot):
    if not snapshot.get("available"):
        return [QualityFinding(rule="lookup", result="verify", reason="景区限制暂时无法查询，请核实景区公告。")]
    findings = []
    destination = request.get("destination", "")
    priority = {"closure": 0, "reservation": 1, "admission": 2}
    for plan in days:
        day = plan.get("day")
        when = trip_day(request, day)
        for attraction in plan.get("attractions", []):
            found = sorted(matches(attraction, destination, snapshot), key=lambda pair: priority[pair[0]["kind"]])
            for rule, basis in found:
                if when is not None and not _applies(rule, when):
                    continue
                kind = rule["kind"]
                if basis == "ambiguous":
                    result, reason = "verify", "同城同名景点的身份无法唯一确认，请核对公告适用景点。"
                elif when is None:
                    result, reason = "verify", "游客未明确出发日期，无法核对游览日是否处于限制期。"
                elif kind == "closure":
                    result, reason = "violation", "游览日落在已发布的闭园期。"
                elif kind == "reservation":
                    result, reason = "notice", "游览日需要预约，请根据要求提前办理。"
                else:
                    result, reason = "notice", "游览日适用入园限制，请查看注意事项。"
                findings.append(QualityFinding(
                    rule=kind, result=result, reason=reason, day=day, visit_date=when,
                    attraction=attraction.get("name"), restriction_id=rule["id"], restriction_version=rule["version"],
                    matched_by=basis, description=rule["description"], source_note=rule["source_note"],
                ))
    return findings


def assess(itinerary, request, snapshot):
    days = itinerary.get("day_plans", [])
    findings = _scenic_findings(days, request, snapshot)
    budget_limit = (request.get("budget") or {}).get("total_cny", request.get("budget_total", 0)) or 0
    total_estimate = itinerary.get("total_budget_estimate_cny", 0)
    if budget_limit > 0 and total_estimate > budget_limit * 1.5:
        findings.append(QualityFinding(rule="budget", result="violation",
                       reason=f"超出预算：预估{total_estimate:.0f}元 vs 预算{budget_limit:.0f}元"))
    for plan in days:
        hours = sum(attraction.get("visit_duration_hours", 2) for attraction in plan.get("attractions", []))
        hours += (plan.get("route") or {}).get("estimated_travel_time_minutes", 0) / 60
        if hours > 12:
            day = plan.get("day")
            findings.append(QualityFinding(rule="duration", result="violation", day=day,
                            visit_date=trip_day(request, day), reason=f"第{day}天行程过满：游览和路途预计{hours:.1f}小时"))
    if not any(plan.get("attractions") for plan in days):
        findings.append(QualityFinding(rule="no_attractions", result="violation", reason="行程中没有景点"))
    results = {item.result for item in findings}
    status = next((result for result in ("violation", "verify", "notice") if result in results), "pass")
    return status, findings


def annotate(itinerary, findings):
    itinerary = deepcopy(itinerary)
    daily, general = {}, []
    for item in findings:
        if item.restriction_id:
            description = f"{item.attraction} · {RESTRICTION_LABELS[item.rule]}。{item.reason} {item.description}（来源：{item.source_note}）"
            daily.setdefault(item.day, []).append(description)
        elif item.rule != "duration":
            general.append(item.reason)
        else:
            daily.setdefault(item.day, []).append(item.reason)
    for plan in itinerary.get("day_plans", []):
        plan["notes"] = _notes(plan.get("notes"), daily.get(plan.get("day"), []))
    itinerary["overall_tips"] = _notes(itinerary.get("overall_tips"), general)
    return itinerary


def _notes(existing, details):
    existing = (existing or "").split(NOTES_START, 1)[0].strip()
    return existing + (NOTES_START + "\n".join(dict.fromkeys(details)) if details else "")


async def save_report(db, trip_id, version, destination, stage, status, findings):
    db.add(PlanningQualityReport(
        trip_id=trip_id, version=version, destination=destination, stage=stage, status=status,
        findings=[finding.model_dump(mode="json") for finding in findings], checked_at=utc_now(),
    ))
    await db.flush()
    for rule in {finding.rule for finding in findings}:
        db.add(PlanningQualityRule(trip_id=trip_id, version=version, rule=rule))
    await db.flush()


def _summary(row):
    return QualitySummary(
        trip_id=row.trip_id, version=row.version, destination=row.destination, stage=row.stage,
        status=row.status, checked_at=row.checked_at,
    )


async def list_reports(db, *, status, rule, limit, offset):
    filters = []
    if status:
        filters.append(PlanningQualityReport.status == status)
    if rule:
        filters.append(exists().where(
            PlanningQualityRule.trip_id == PlanningQualityReport.trip_id,
            PlanningQualityRule.version == PlanningQualityReport.version, PlanningQualityRule.rule == rule,
        ))
    total = await db.scalar(select(func.count()).select_from(PlanningQualityReport).where(*filters))
    rows = await db.scalars(select(PlanningQualityReport).where(*filters)
        .order_by(PlanningQualityReport.checked_at.desc(), PlanningQualityReport.trip_id,
                  PlanningQualityReport.version.desc()).limit(limit).offset(offset))
    return ResourcePage[QualitySummary](total=total or 0, items=[_summary(row) for row in rows])


async def get_report(db, trip_id, version):
    row = await db.get(PlanningQualityReport, (trip_id, version))
    if row:
        return QualityDetail(**_summary(row).model_dump(), findings=row.findings)
    # The old trip's existence and version can only be exposed once confirmed.
    destination = await db.scalar(select(Trip.destination).where(
        Trip.id == trip_id, Trip.status == "completed",
        or_(Trip.version == version, Trip.confirmed_version == version,
            exists().where(TripVersion.trip_id == Trip.id, TripVersion.version == version)),
    ))
    if destination is None:
        raise HTTPException(404, "未找到该行程版本")
    return QualityDetail(trip_id=trip_id, version=version, destination=destination,
                         status="unchecked", stage=None, checked_at=None, findings=[])
