"""Fetches weather + team schedules and writes site/data.json.

Runs on GitHub Actions every 15 minutes. The pages in site/ only read data.json.
"""
import json
import os
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")
LAT, LON = 33.63, -117.92  # Newport Beach, CA (ZIP 92627)

# (display name, league label, ESPN sport/league path, ESPN team slug or id)
TEAMS = [
    ("Packers", "NFL", "football/nfl", "gb"),
    ("Chiefs", "NFL", "football/nfl", "kc"),
    ("Texans", "NFL", "football/nfl", "hou"),
    ("Huskers", "NCAA", "football/college-football", "158"),
    ("Ducks", "NHL", "hockey/nhl", "ana"),
    ("Angels", "MLB", "baseball/mlb", "laa"),
]

WEATHER = {
    0: ("Clear", "☀️"), 1: ("Mostly clear", "\U0001F324️"),
    2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁️"),
    45: ("Fog", "\U0001F32B️"), 48: ("Fog", "\U0001F32B️"),
    51: ("Light drizzle", "\U0001F326️"), 53: ("Drizzle", "\U0001F326️"),
    55: ("Drizzle", "\U0001F326️"), 61: ("Light rain", "\U0001F327️"),
    63: ("Rain", "\U0001F327️"), 65: ("Heavy rain", "\U0001F327️"),
    80: ("Showers", "\U0001F327️"), 81: ("Showers", "\U0001F327️"),
    82: ("Heavy showers", "\U0001F327️"), 95: ("Thunderstorm", "⛈️"),
}


def get_json(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "home-dash (github.com/CMLP935161/home_projects)",
                 "Accept": "application/geo+json, application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def build_weather_openmeteo():
    w = get_json(
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        "&current=temperature_2m,weather_code"
        "&daily=temperature_2m_max,temperature_2m_min,weather_code"
        "&temperature_unit=fahrenheit&timezone=America%2FLos_Angeles"
        "&forecast_days=4"
    )
    cur = w["current"]
    desc, icon = WEATHER.get(cur["weather_code"], ("", ""))
    d = w["daily"]
    days = []
    for i in range(1, 4):
        _, ic = WEATHER.get(d["weather_code"][i], ("", ""))
        days.append({
            "day": datetime.fromisoformat(d["time"][i]).strftime("%a"),
            "hi": round(d["temperature_2m_max"][i]),
            "lo": round(d["temperature_2m_min"][i]),
            "icon": ic,
        })
    return {
        "temp": round(cur["temperature_2m"]),
        "desc": desc,
        "icon": icon,
        "hi": round(d["temperature_2m_max"][0]),
        "lo": round(d["temperature_2m_min"][0]),
        "days": days,
    }


def icon_for(text):
    t = (text or "").lower()
    if "thunder" in t:
        return "⛈️"
    if "rain" in t or "shower" in t or "drizzle" in t:
        return "\U0001F327️"
    if "snow" in t:
        return "❄️"
    if "fog" in t or "haze" in t or "smoke" in t:
        return "\U0001F32B️"
    if "partly" in t:
        return "⛅"
    if "mostly sunny" in t or "mostly clear" in t:
        return "\U0001F324️"
    if "cloud" in t or "overcast" in t:
        return "☁️"
    if "sunny" in t or "clear" in t:
        return "☀️"
    return ""


def build_weather_nws(now):
    """National Weather Service: real station observations + official forecast."""
    pts = get_json(f"https://api.weather.gov/points/{LAT:.4f},{LON:.4f}")["properties"]

    # Current conditions: first nearby station that reports a temperature.
    temp = desc = None
    stations = get_json(pts["observationStations"])["features"][:5]
    for st in stations:
        sid = st["properties"]["stationIdentifier"]
        try:
            obs = get_json(f"https://api.weather.gov/stations/{sid}/observations/latest")["properties"]
        except Exception:
            continue
        c = (obs.get("temperature") or {}).get("value")
        if c is not None:
            temp = round(c * 9 / 5 + 32)
            desc = obs.get("textDescription") or ""
            break
    if temp is None:
        raise ValueError("no NWS station reported a temperature")

    # Forecast periods -> one entry per calendar day.
    periods = get_json(pts["forecast"])["properties"]["periods"]
    by_day = {}
    for p in periods:
        day = p["startTime"][:10]
        e = by_day.setdefault(day, {"hi": None, "lo": None, "text": ""})
        if p.get("isDaytime"):
            e["hi"] = p["temperature"]
            e["text"] = p.get("shortForecast", "")
        else:
            e["lo"] = p["temperature"]
            if not e["text"]:
                e["text"] = p.get("shortForecast", "")
    keys = sorted(by_day)
    today_key = now.strftime("%Y-%m-%d")
    today = by_day.get(today_key, {"hi": None, "lo": None, "text": ""})
    days = []
    for k in [k for k in keys if k > today_key][:3]:
        e = by_day[k]
        days.append({
            "day": datetime.fromisoformat(k).strftime("%a"),
            "hi": e["hi"], "lo": e["lo"], "icon": icon_for(e["text"]),
        })
    return {
        "temp": temp,
        "desc": desc,
        "icon": icon_for(desc),
        "hi": today["hi"],
        "lo": today["lo"],
        "days": days,
    }


def build_weather(now):
    try:
        return build_weather_nws(now)
    except Exception:
        return build_weather_openmeteo()


# ---------- sports ----------

def fetch_schedule(path, team, season=None):
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams/{team}/schedule"
    if season:
        url += f"?season={season}"
    return get_json(url)


def score_of(c):
    s = c.get("score")
    if isinstance(s, dict):
        if s.get("displayValue") not in (None, ""):
            return str(s["displayValue"])
        if s.get("value") is not None:
            return str(int(s["value"]))
        return None
    return None if s in (None, "") else str(s)


def parse_events(data):
    my_id = str(data.get("team", {}).get("id", ""))
    my_abbr = data.get("team", {}).get("abbreviation", "")
    out = []
    for ev in data.get("events", []):
        try:
            comp = ev["competitions"][0]
            when = datetime.fromisoformat(comp.get("date", ev["date"]).replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            st = comp["status"]["type"]
            me = opp = None
            for c in comp["competitors"]:
                t = c.get("team", {})
                if str(t.get("id")) == my_id or (not my_id and t.get("abbreviation") == my_abbr):
                    me = c
                else:
                    opp = c
            if me is None or opp is None:
                continue
            out.append({
                "when": when.astimezone(TZ),
                "state": st.get("state", "pre"),  # pre / in / post
                "detail": st.get("shortDetail", ""),
                "home": me.get("homeAway") == "home",
                "opp": opp.get("team", {}).get("abbreviation")
                       or opp.get("team", {}).get("shortDisplayName", "?"),
                "my_score": score_of(me),
                "opp_score": score_of(opp),
                "winner": me.get("winner"),
            })
        except (KeyError, IndexError, ValueError):
            continue
    out.sort(key=lambda e: e["when"])
    return out


def summarize(events, now):
    """Return (headline, subline, live)."""
    live = [e for e in events if e["state"] == "in"]
    done = [e for e in events if e["state"] == "post"]
    nxt = [e for e in events if e["state"] == "pre" and e["when"] >= now]

    def vs(e):
        return ("vs " if e["home"] else "@ ") + e["opp"]

    if live:
        e = live[0]
        return f"{e['my_score']}-{e['opp_score']} {vs(e)}", "LIVE: " + e["detail"], True

    head, sub = "", ""
    if done:
        e = done[-1]
        try:
            a, b = int(e["my_score"]), int(e["opp_score"])
            won = e["winner"] if e["winner"] is not None else a > b
            res = "T" if a == b else ("W" if won else "L")
        except (TypeError, ValueError):
            res = ""
        head = f"{res} {e['my_score']}-{e['opp_score']} {vs(e)}".strip()
        sub = "Final, " + e["when"].strftime("%a %-m/%-d")
    if nxt:
        n = nxt[0]
        t = "Next: " + n["when"].strftime("%a %-m/%-d %-I:%M %p") + " " + vs(n)
        sub = (sub + "  |  " if sub else "") + t
    if done and not nxt and (now - done[-1]["when"]).days > 30:
        sub += "  |  Offseason"
    if not head and not nxt:
        head = "No games"
    return head, sub, False


def build_teams(now):
    out = []
    for name, league, path, team in TEAMS:
        try:
            events = parse_events(fetch_schedule(path, team))
            if not events:  # offseason: the feed may default to an empty new season
                for yr in (now.year, now.year - 1):
                    events = parse_events(fetch_schedule(path, team, yr))
                    if events:
                        break
            head, sub, live = summarize(events, now)
        except Exception:
            head, sub, live = "Unavailable", "", False
        out.append({"name": name, "league": league, "head": head, "sub": sub, "live": live})
    return out


def read_notes():
    try:
        with open("notes.txt", encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()][:5]
    except FileNotFoundError:
        return []


def main():
    now = datetime.now(TZ)
    try:
        weather = build_weather(now)
    except Exception:
        weather = None
    data = {
        "updated": now.strftime("%-I:%M %p"),
        "updated_epoch": int(now.timestamp()),
        "weather": weather,
        "teams": build_teams(now),
        "notes": read_notes(),
    }
    os.makedirs("site", exist_ok=True)
    with open("site/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
