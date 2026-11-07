"""Fetches weather + team schedules and writes site/data.json.

Runs on GitHub Actions every 15 minutes. The pages in site/ only read data.json.
"""
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
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
        if n["when"].date() == now.date():
            when_txt = "Today " + n["when"].strftime("%-I:%M %p")
        else:
            when_txt = n["when"].strftime("%a %-m/%-d %-I:%M %p")
        t = "Next: " + when_txt + " " + vs(n)
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


# ---------- day-aware scoreboard ----------

FAV_ABBR = {"NFL": {"GB", "KC", "HOU"}, "NCAA": {"NEB"}, "NHL": {"ANA"}, "MLB": {"LAA"}}
LEAGUE_PATHS = {
    "NFL": "football/nfl",
    "NCAA": "football/college-football",
    "NHL": "hockey/nhl",
    "MLB": "baseball/mlb",
}
TODAY_LEAGUES = ("NFL", "NCAA", "NHL", "MLB")


def fetch_scoreboard(league, now):
    url = (
        f"https://site.api.espn.com/apis/site/v2/sports/{LEAGUE_PATHS[league]}"
        f"/scoreboard?dates={now.strftime('%Y%m%d')}"
    )
    if league == "NCAA":
        url += "&groups=80&limit=200"  # FBS only
    return get_json(url)


def parse_game(ev, league):
    comp = ev["competitions"][0]
    st = (comp.get("status") or ev.get("status") or {}).get("type", {})
    state = st.get("state", "pre")
    when = datetime.fromisoformat((comp.get("date") or ev["date"]).replace("Z", "+00:00"))
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    when = when.astimezone(TZ)
    sides = {}
    ids = {}
    for c in comp["competitors"]:
        t = c.get("team", {})
        abbr = t.get("abbreviation") or t.get("shortDisplayName", "?")
        ids[str(t.get("id"))] = abbr
        rank = (c.get("curatedRank") or {}).get("current")
        rank = rank if isinstance(rank, int) and 1 <= rank <= 25 else None
        fav = abbr in FAV_ABBR[league] or (league == "NCAA" and str(t.get("id")) == "158")
        sides[c.get("homeAway")] = {
            "abbr": abbr,
            "score": score_of(c) if state != "pre" else None,
            "rank": rank,
            "fav": fav,
            "win": bool(c.get("winner")),
        }
    away, home = sides["away"], sides["home"]
    if state == "pre":
        status = when.strftime("%-I:%M %p")
    else:
        status = st.get("shortDetail") or st.get("description") or ""
    # Football only: who has the ball, down & distance, and red zone (live games).
    poss = down = None
    redzone = False
    if league in ("NFL", "NCAA") and state == "in":
        sit = comp.get("situation") or {}
        poss = ids.get(str(sit.get("possession")))
        down = sit.get("shortDownDistanceText") or sit.get("downDistanceText") or None
        redzone = bool(sit.get("isRedZone"))
    return {
        "poss": poss,
        "down": down,
        "redzone": redzone,
        "league": league,
        "away": away,
        "home": home,
        "status": status,
        "state": state,
        "live": state == "in",
        "fav": away["fav"] or home["fav"],
        "when": when.timestamp(),
    }


def games_for(league, now):
    out = []
    for ev in fetch_scoreboard(league, now).get("events", []):
        try:
            out.append(parse_game(ev, league))
        except (KeyError, IndexError, ValueError, TypeError):
            continue
    return out


def nebraska_week_game(now):
    """Nebraska's game this college-football week (Tuesday to Monday), whatever
    day it is played: Thursday/Friday games and bye weeks are handled."""
    delta = (now.weekday() - 1) % 7  # days since Tuesday
    start = (now - timedelta(days=delta)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    events = [
        e for e in parse_events(fetch_schedule("football/college-football", "158"))
        if start <= e["when"] < end
    ]
    if not events:
        return None
    e = events[0]
    pre = e["state"] == "pre"
    me = {"abbr": "NEB", "score": None if pre else e["my_score"], "rank": None,
          "fav": True, "win": e["winner"] is True}
    opp = {"abbr": e["opp"], "score": None if pre else e["opp_score"], "rank": None,
           "fav": False, "win": e["winner"] is False}
    if pre:
        status = e["when"].strftime("%a %-I:%M %p")
    elif e["state"] == "in":
        status = e["detail"]
    else:
        status = e["detail"] or "Final"
        if e["when"].date() != now.date():
            status += ", " + e["when"].strftime("%a")
    return {
        "poss": None, "down": None, "redzone": False,
        "league": "NCAA",
        "away": opp if e["home"] else me,
        "home": me if e["home"] else opp,
        "status": status,
        "state": e["state"],
        "live": e["state"] == "in",
        "fav": True,
        "when": e["when"].timestamp(),
    }


def build_view(now):
    """Saturday: Nebraska + Top 25 matchups. Sunday: full NFL slate.
    Nebraska's game for the week always appears. Any day: favorite teams that
    play today. Otherwise 'favorites' mode."""
    dow = now.weekday()  # Mon=0 ... Sat=5, Sun=6
    sections, used = [], set()

    if dow == 5:
        games = games_for("NCAA", now)
        feats = [g for g in games if g["fav"]]
        top = [g for g in games if not g["fav"] and g["away"]["rank"] and g["home"]["rank"]]
        top.sort(key=lambda g: (min(g["away"]["rank"], g["home"]["rank"]), g["when"]))
        picked = (feats + top)[:10]
        if picked:
            sections.append({"key": "NCAA", "title": "College Football · Top 25", "games": picked})
            used.add("NCAA")
    elif dow == 6:
        games = games_for("NFL", now)
        games.sort(key=lambda g: (not g["fav"], g["when"]))
        if games:
            sections.append({"key": "NFL", "title": "NFL", "games": games[:16]})
            used.add("NFL")

    neb = None
    if dow == 5:  # Saturday only: Nebraska stays with the other college games
        try:
            neb = nebraska_week_game(now)
        except Exception:
            neb = None

    def is_neb(g):
        return g["away"]["abbr"] == "NEB" or g["home"]["abbr"] == "NEB"

    neb_in_sections = any(is_neb(g) for s in sections for g in s["games"])
    if neb and not neb_in_sections and dow == 5:
        ncaa = next((s for s in sections if s["key"] == "NCAA"), None)
        if ncaa:
            ncaa["games"].insert(0, neb)
        else:
            sections.append({"key": "NCAA", "title": "College Football · Top 25", "games": [neb]})
            used.add("NCAA")
        neb_in_sections = True

    if not sections:
        return {"mode": "favorites", "sections": []}

    extra = []
    for lg in TODAY_LEAGUES:
        if lg in used or (lg == "NCAA" and dow == 6):  # college stays out of Sundays
            continue
        try:
            extra += [g for g in games_for(lg, now) if g["fav"]]
        except Exception:
            continue
    extra.sort(key=lambda g: g["when"])
    if extra:
        sections.append({"key": "TODAY", "title": "Your teams", "games": extra})
    return {"mode": "slate", "sections": sections}


def safe_view(now):
    try:
        return build_view(now)
    except Exception:
        return {"mode": "favorites", "sections": []}


def read_notes():
    try:
        with open("notes.txt", encoding="utf-8") as f:
            # blank lines and lines starting with # are ignored
            return [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")][:5]
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
        "view": safe_view(now),
        "notes": read_notes(),
    }
    os.makedirs("site", exist_ok=True)
    with open("site/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
