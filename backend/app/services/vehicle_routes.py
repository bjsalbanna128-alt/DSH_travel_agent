"""Vehicle candidates from the saved route and explicit traveler information."""

import math
import re
from datetime import timedelta

from app.schemas.fleet import VehicleLeg, VehicleOffer
from app.services.geo import haversine_km
from app.services.scenic_restrictions import city_key, name_key
from app.services.transport_plan import intraday_pairs, travel_minutes

DURATIONS = {"airport_transfer": 120, "charter": 600}
_CAPITAL = r"(?:北京\s*)?(?:首都\s*(?:国际)?机场|PEK)"
_DAXING = r"(?:北京\s*)?(?:大兴\s*(?:国际)?机场|PKX)"
_DISTRICTS = "东城|西城|朝阳|海淀|丰台|石景山|通州|顺义|昌平|大兴|房山|门头沟|怀柔|平谷|密云|延庆"


def airport_name(value):
    value = (value or "").strip()
    match = re.fullmatch(rf"{_CAPITAL}\s*(?:T\s*([123])|([123])号航站楼)(?:\s*航站楼)?", value, re.I)
    if match:
        return f"北京首都机场 T{match[1] or match[2]}"
    if re.fullmatch(rf"{_DAXING}(?:\s*(?:航站楼|主航站楼))?", value, re.I):
        return "北京大兴机场"
    return None


def explicit_arrival(query):
    if re.search(r"(?:改坐|改乘|坐|乘|搭)\s*(?:高铁|火车|动车)|不(?:坐|乘|搭)飞机|不用接机", query):
        return {"mode": "other"}
    if not re.search(r"乘机|乘飞机|坐飞机|搭飞机|飞抵|飞到|航班|接机", query):
        return None
    if re.search(r"飞机(?:或|还是)火车|火车(?:或|还是)飞机|(?:可能|也许|考虑)\s*(?:坐飞机|乘机|乘飞机)", query):
        return None
    arrival = {"mode": "flight"}
    airport = re.search(rf"{_CAPITAL}\s*(?:T\s*[123]|[123]号航站楼)(?:\s*航站楼)?|{_DAXING}", query, re.I)
    if airport and (place := airport_name(airport[0])):
        arrival["pickup"] = place
    time_match = re.search(r"(?<![0-9])([01]?[0-9]|2[0-3])[:：]([0-5][0-9])(?![0-9])", query)
    if time_match:
        arrival["start_time"] = f"{int(time_match[1]):02d}:{time_match[2]}"
    dropoff = re.search(r"(?:送到|送达|送我到)\s*([^，。；\n]{2,90})", query)
    if dropoff:
        arrival["dropoff"] = dropoff[1].strip()
    return arrival


def destination_allowed(value, day_plans):
    if not value.strip() or any(mark in value for mark in ("跨城", "河北省", "天津市")):
        return False
    for plan in day_plans:
        for stop in [plan.get("hotel") or {}, *(plan.get("attractions") or [])]:
            if stop.get("name") and name_key(stop["name"]) == name_key(value):
                return city_key(stop.get("city") or "北京") == "北京"
    return bool(re.fullmatch(rf"(?:北京市?\s*)?(?:{_DISTRICTS})区\s*\S.{{1,145}}", value.strip()))


def _measurable(stop):
    location = stop["location"]
    if not isinstance(location, dict):
        return False
    lat, lng = location.get("lat"), location.get("lng")
    return (type(lat) in (int, float) and type(lng) in (int, float)
            and math.isfinite(lat) and math.isfinite(lng) and abs(lat) <= 90 and abs(lng) <= 180
            and (lat != 0 or lng != 0))


def build_vehicle_offers(day_plans, request, destination, start=None):
    if city_key(destination or "") != "北京":
        return []
    plans = {plan["day"]: plan for plan in day_plans if type(plan.get("day")) is int and plan["day"] >= 1}
    if not plans:
        return []
    result = []
    for day, plan in sorted(plans.items()):
        try:
            date = start + timedelta(days=day - 1) if start else None
        except OverflowError:
            continue
        hotel = plan.get("hotel")
        prev_hotel = (plans.get(day - 1) or {}).get("hotel")
        if day == 1:
            arrival = request.get("flight_arrival") or {}
            explicit = arrival.get("mode") == "flight"
            result.append(VehicleOffer(
                service_key="vehicle:1:airport_transfer", purpose="airport_transfer", day=day,
                service_date=date, duration_minutes=DURATIONS["airport_transfer"],
                pickup=airport_name(arrival.get("pickup", "")) or "" if explicit else "",
                dropoff=arrival.get("dropoff") if explicit and arrival.get("dropoff") else (hotel or {}).get("name", ""),
                suggested_start=arrival.get("start_time") if explicit else None,
                recommended=explicit, reason="已提供乘机到达信息" if explicit else "首日可按需添加接机",
            ))
        mode = (plan.get("route") or {}).get("travel_mode") or "walking"
        stops = [prev_hotel, hotel, *(plan.get("attractions") or [])]
        if any(stop and stop.get("city") and city_key(stop["city"]) != "北京" for stop in stops):
            continue
        legs = []
        for a, b in intraday_pairs(plan.get("attractions"), prev_hotel or hotel, hotel):
            distance = haversine_km(a, b) if _measurable(a) and _measurable(b) else None
            legs.append(VehicleLeg(
                origin=a["name"], destination=b["name"],
                distance_km=round(distance, 2) if distance is not None else None,
                duration_minutes=travel_minutes(distance, mode) if distance is not None else None,
            ))
        if not legs:
            continue
        distance = sum(item.distance_km or 0 for item in legs)
        minutes = sum(item.duration_minutes or 0 for item in legs)
        recommended = distance >= 8 or minutes >= 60
        result.append(VehicleOffer(
            service_key=f"vehicle:{day}:charter", purpose="charter", day=day, service_date=date,
            pickup=legs[0].origin, dropoff=legs[-1].destination, legs=legs,
            suggested_start="09:00", duration_minutes=DURATIONS["charter"], recommended=recommended,
            reason="累计路程或移动时长达到包车推荐条件" if recommended else "可按需选择当天包车",
        ))
    return result
