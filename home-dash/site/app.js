/* ES5 on purpose: older Fire tablets run an older browser. */
var DATA = null;

function $(id) { return document.getElementById(id); }
function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function tick() {
  var d = new Date();
  var h = d.getHours(), m = d.getMinutes();
  var ap = h >= 12 ? "PM" : "AM";
  h = h % 12; if (h === 0) { h = 12; }
  if ($("clock")) { $("clock").innerHTML = h + ":" + (m < 10 ? "0" : "") + m + " <span style='font-size:.35em;color:#9fb0c3'>" + ap + "</span>"; }
  if ($("date")) {
    var days = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
    var mons = ["January","February","March","April","May","June","July","August","September","October","November","December"];
    $("date").innerHTML = "<span class='wd'>" + days[d.getDay()] + "</span><span class='md'>" + mons[d.getMonth()] + " " + d.getDate() + "</span>";
  }
  checkStale();
  if (LIVE.maxUntil && new Date().getTime() > LIVE.maxUntil) { LIVE.maxUntil = 0; render(); }
}

function checkStale() {
  if (!DATA || !$("stale")) { return; }
  var ageMin = (new Date().getTime() / 1000 - DATA.updated_epoch) / 60;
  $("stale").innerHTML = ageMin > 120 ? "Data is " + Math.round(ageMin / 60) + "h old" : "";
}

var LG_COLORS = { NFL: "#4aa3ff", NCAA: "#ff7a59", NHL: "#7bd88f", MLB: "#f2c14e", TODAY: "#c9a0ff", NEXT: "#8ecae6" };

/* ---- live updates: poll ESPN straight from the tablet while a game is live ---- */
var POLL_MS = (function () {
  var m = /[?&]poll=(\d+)/.exec(location.search);
  return (m ? parseInt(m[1], 10) : 30) * 1000;
})();
var LIVE = { prev: {}, flash: {}, seeded: {}, maxUntil: 0 };
var LG_PATHS = { NFL: "football/nfl", NCAA: "football/college-football", NHL: "hockey/nhl", MLB: "baseball/mlb" };

function pad2(n) { return (n < 10 ? "0" : "") + n; }

function scoreStr(s) {
  if (s === null || s === undefined || s === "") { return null; }
  if (typeof s === "object") {
    if (s.displayValue !== undefined && s.displayValue !== null) { return String(s.displayValue); }
    return s.value !== undefined && s.value !== null ? String(Math.round(s.value)) : null;
  }
  return String(s);
}

function clock12(d) {
  var h = d.getHours(), ap = h >= 12 ? "PM" : "AM";
  h = h % 12; if (h === 0) { h = 12; }
  return h + ":" + pad2(d.getMinutes()) + " " + ap;
}

function parseScoreboard(json, league) {
  var out = {}, evs = (json && json.events) || [];
  for (var i = 0; i < evs.length; i++) {
    try {
      var ev = evs[i], comp = ev.competitions[0];
      var st = ((comp.status || ev.status || {}).type) || {};
      var state = st.state || "pre";
      var sides = {}, ids = {};
      for (var j = 0; j < comp.competitors.length; j++) {
        var c = comp.competitors[j], t = c.team || {};
        var abbr = t.abbreviation || t.shortDisplayName || "?";
        ids[String(t.id)] = abbr;
        sides[c.homeAway] = { abbr: abbr, score: state === "pre" ? null : scoreStr(c.score), win: !!c.winner };
      }
      var football = (league === "NFL" || league === "NCAA");
      var sit = (football && state === "in") ? (comp.situation || {}) : {};
      out[sides.away.abbr + "@" + sides.home.abbr] = {
        away: sides.away, home: sides.home, state: state, live: state === "in",
        status: state === "pre" ? clock12(new Date(comp.date || ev.date)) : (st.shortDetail || st.description || ""),
        poss: ids[String(sit.possession)] || null,
        down: sit.downDistanceText || sit.shortDownDistanceText || null,
        redzone: !!sit.isRedZone
      };
    } catch (e) {}
  }
  return out;
}

function scoreLabel(delta, league) {
  if (league !== "NFL" && league !== "NCAA") { return "SCORE"; }
  if (delta === 6 || delta === 7 || delta === 8) { return "TD"; }
  if (delta === 3) { return "FG"; }
  if (delta === 2) { return "SAFETY"; }
  if (delta === 1) { return "XP"; }
  return "SCORE";
}

function applyLive(league, map) {
  if (!DATA || !DATA.view) { return; }
  var firstTime = !LIVE.seeded[league];
  LIVE.seeded[league] = true;
  var now = new Date().getTime();
  for (var i = 0; i < DATA.view.sections.length; i++) {
    var games = DATA.view.sections[i].games || [];
    for (var j = 0; j < games.length; j++) {
      var g = games[j];
      if (g.league !== league) { continue; }
      var key = g.away.abbr + "@" + g.home.abbr, L = map[key];
      if (!L) { continue; }
      var pk = league + key, a = parseInt(L.away.score, 10), h = parseInt(L.home.score, 10);
      if (!isNaN(a) && !isNaN(h)) {
        var p = LIVE.prev[pk];
        if (p && !firstTime) {
          if (a > p.a) { LIVE.flash[pk] = { team: L.away.abbr, label: scoreLabel(a - p.a, league), until: now + 120000 }; }
          else if (h > p.h) { LIVE.flash[pk] = { team: L.home.abbr, label: scoreLabel(h - p.h, league), until: now + 120000 }; }
          if (LIVE.flash[pk] && LIVE.flash[pk].until > LIVE.maxUntil) { LIVE.maxUntil = LIVE.flash[pk].until; }
        }
        LIVE.prev[pk] = { a: a, h: h };
      }
      g.away.score = L.away.score; g.home.score = L.home.score;
      g.away.win = L.away.win; g.home.win = L.home.win;
      g.state = L.state; g.live = L.live; g.status = L.status;
      g.poss = L.poss; g.down = L.down; g.redzone = L.redzone;
    }
  }
}

function anyLive() {
  if (!DATA || !DATA.view || DATA.view.mode !== "slate") { return false; }
  for (var i = 0; i < DATA.view.sections.length; i++) {
    var gs = DATA.view.sections[i].games || [];
    for (var j = 0; j < gs.length; j++) {
      if (gs[j].live) { return true; }
    }
  }
  return false;
}

var LAST_POLL = 0;
function dataAgeMin() {
  return DATA && DATA.updated_epoch ? (new Date().getTime() / 1000 - DATA.updated_epoch) / 60 : 0;
}
function pollLive() {
  /* poll while a game is live, or (slower) when the built data has gone stale,
     e.g. GitHub skipped scheduled rebuilds */
  var live = anyLive();
  if (!DATA || !DATA.view || DATA.view.mode !== "slate") { return; }
  if (!live) {
    if (dataAgeMin() < 20) { return; }
    var t = new Date().getTime();
    if (t - LAST_POLL < 120000) { return; }
    LAST_POLL = t;
  }
  var leagues = {}, d = new Date();
  var ymd = d.getFullYear() + pad2(d.getMonth() + 1) + pad2(d.getDate());
  for (var i = 0; i < DATA.view.sections.length; i++) {
    var gs = DATA.view.sections[i].games || [];
    for (var j = 0; j < gs.length; j++) { leagues[gs[j].league] = true; }
  }
  for (var lg in leagues) {
    if (leagues.hasOwnProperty(lg) && LG_PATHS[lg]) { fetchLeague(lg, ymd); }
  }
}

function fetchLeague(lg, ymd) {
  var url = "https://site.api.espn.com/apis/site/v2/sports/" + LG_PATHS[lg] + "/scoreboard?dates=" + ymd +
    (lg === "NCAA" ? "&groups=80&limit=200" : "");
  var x = new XMLHttpRequest();
  x.open("GET", url, true);
  x.onreadystatechange = function () {
    if (x.readyState === 4 && x.status === 200) {
      try { applyLive(lg, parseScoreboard(JSON.parse(x.responseText), lg)); render(); } catch (e) {}
    }
  };
  try { x.send(); } catch (e) {}
}

function activeFlash(key) {
  var f = LIVE.flash[key];
  return f && f.until > new Date().getTime() ? f : null;
}

function teamHtml(s, flash, poss) {
  var rk = s.rank ? "<i class='rk'>" + s.rank + "</i>" : "";
  var ball = poss && poss === s.abbr ? "<span class='ball'>&#127944;</span>" : "";
  var fl = flash && flash.team === s.abbr ? "<span class='flash'>" + esc(flash.label) + "</span>" : "";
  return "<span class='tm" + (s.fav ? " fv" : "") + "'>" + rk + esc(s.abbr) + ball + fl + "</span>";
}

function gameHtml(g) {
  var a = g.away, h = g.home, mid;
  if (a.score !== null && a.score !== undefined && h.score !== null && h.score !== undefined) {
    mid = "<span class='sc" + (a.win ? " w" : "") + "'>" + esc(a.score) + "</span>" +
          "<span class='dash'>&ndash;</span>" +
          "<span class='sc" + (h.win ? " w" : "") + "'>" + esc(h.score) + "</span>";
  } else {
    mid = "<span class='dash'>@</span>";
  }
  var color = g.live ? "#ff5252" : (g.fav ? (LG_COLORS[g.league] || "#9fb0c3") : "#2b3a4d");
  var fl = activeFlash(g.league + a.abbr + "@" + h.abbr);
  var st = esc(g.status);
  if (g.redzone) { st = "<span class='rz'>RED ZONE</span> " + st; }
  var dn = g.down ? "<div class='dn'>" + esc(g.down) + "</div>" : "";
  return "<div class='g'><div class='gi" + (g.live ? " live" : "") + (g.redzone ? " redz" : "") + "' style='border-left-color:" + color + "'>" +
    "<div class='gm'>" + teamHtml(a, fl, g.poss) + mid + teamHtml(h, fl, g.poss) + "</div>" +
    "<div class='gs'>" + st + dn + "</div></div></div>";
}

function cardHtml(c) {
  var parts = [];
  if (c.line) { parts.push("Line " + esc(c.line)); }
  if (c.ou !== null && c.ou !== undefined) { parts.push("O/U " + esc(c.ou)); }
  var odds = parts.length ? parts.join(" &middot; ") : "<span class='nolx'>Line not posted yet</span>";
  return "<div class='nc'><div class='nr'><span class='nt'>" + esc(c.team) + "</span>" +
    (c.tv ? "<span class='ntv'>" + esc(c.tv) + "</span>" : "") + "</div>" +
    "<div class='nm'>" + esc(c.matchup) + " &middot; " + esc(c.when) + "</div>" +
    "<div class='nl'>" + odds + "</div></div>";
}

function renderSlate(sections) {
  var out = "<div class='slate'>";
  for (var i = 0; i < sections.length; i++) {
    var sec = sections[i];
    out += "<div class='lgh' style='color:" + (LG_COLORS[sec.key] || "#9fb0c3") + "'>" + esc(sec.title) + "</div>";
    if (sec.cards) {
      out += "<div class='cards" + (sec.cards.length === 1 ? " one" : "") + "'>";
      for (var k = 0; k < sec.cards.length; k++) { out += cardHtml(sec.cards[k]); }
      out += "</div>";
    } else {
      out += "<div class='games'>";
      for (var j = 0; j < sec.games.length; j++) { out += gameHtml(sec.games[j]); }
      out += "</div>";
    }
  }
  return out + "</div>";
}

function render() {
  if (!DATA) { return; }
  var w = DATA.weather;
  if ($("temp")) {
    if (w) {
      $("temp").innerHTML = w.icon + " " + w.temp + "&deg;";
      if ($("wdesc")) {
        var hl = (w.hi !== null && w.lo !== null) ? " &middot; H " + w.hi + "&deg; L " + w.lo + "&deg;" : "";
        $("wdesc").innerHTML = esc(w.desc || "") + hl;
      }
      if ($("days")) {
        var h = "";
        for (var i = 0; i < w.days.length; i++) {
          var x = w.days[i];
          var hi = x.hi !== null ? x.hi + "&deg;" : "--";
          var lo = x.lo !== null ? x.lo + "&deg;" : "--";
          h += "<div class='day'><b>" + x.day + "</b>" + x.icon + " " + hi + "/" + lo + "</div>";
        }
        $("days").innerHTML = h;
      }
    } else {
      $("temp").innerHTML = "--";
      if ($("wdesc")) { $("wdesc").innerHTML = "Weather unavailable"; }
    }
  }
  if ($("extras")) {
    var ex = DATA.extras || {}, eh = "";
    if (ex.sun) {
      eh += "<div class='ex'><span class='exl'>Sun</span><span class='exv'><i class='up'>&#9650;</i> " + esc(ex.sun.rise) +
            "</span><span class='exv'><i class='dn2'>&#9660;</i> " + esc(ex.sun.set) + "</span></div>";
    }
    if (ex.aqi) {
      var a = ex.aqi.aqi, ac = a <= 50 ? "#7bd88f" : a <= 100 ? "#f2c14e" : a <= 150 ? "#ff9f43" : "#ff6b6b";
      eh += "<div class='ex'><span class='exl'>Air quality</span><span class='exv'><i class='dot' style='background:" + ac +
            "'></i> " + a + "</span><span class='exs'>" + esc(ex.aqi.label) + "</span></div>";
    }
    if (ex.humidity !== null && ex.humidity !== undefined) {
      eh += "<div class='ex'><span class='exl'>Humidity</span><span class='exv'>" + ex.humidity + "%</span></div>";
    }
    $("extras").innerHTML = eh;
    $("extras").style.display = eh ? "" : "none";
  }
  if ($("scores") && DATA.view && DATA.view.mode === "slate") {
    $("scores").innerHTML = renderSlate(DATA.view.sections);
  } else if ($("scores")) {
    // Group teams by league, keeping the order they first appear in.
    var order = [], groups = {};
    for (var j = 0; j < DATA.teams.length; j++) {
      var t = DATA.teams[j];
      if (!groups[t.league]) { groups[t.league] = []; order.push(t.league); }
      groups[t.league].push(t);
    }
    var titles = { NFL: "NFL", NCAA: "College Football", NHL: "NHL", MLB: "MLB" };
    var colors = { NFL: "#4aa3ff", NCAA: "#ff7a59", NHL: "#7bd88f", MLB: "#f2c14e" };
    // First league fills the left column; the rest stack in the right column.
    var cols = ["", ""];
    for (var g = 0; g < order.length; g++) {
      var lg = order[g], col = g === 0 ? 0 : 1;
      var c = colors[lg] || "#9fb0c3";
      cols[col] += "<div class='lgh' style='color:" + c + "'>" + esc(titles[lg] || lg) + "</div>";
      for (var k = 0; k < groups[lg].length; k++) {
        var tm = groups[lg][k];
        cols[col] += "<div class='card" + (tm.live ? " live" : "") + "'><div class='in' style='border-left-color:" + c + "'>" +
          "<div class='row'><span class='name'>" + esc(tm.name) + "</span>" +
          "<span class='head'>" + esc(tm.head) + "</span></div>" +
          "<div class='sub'>" + esc(tm.sub) + "</div></div></div>";
      }
    }
    $("scores").innerHTML = "<div class='col'>" + cols[0] + "</div><div class='col'>" + cols[1] + "</div>";
  }
  if ($("notes")) {
    var n = "";
    for (var k = 0; k < DATA.notes.length; k++) { n += "<div>" + esc(DATA.notes[k]) + "</div>"; }
    $("notes").innerHTML = n;
    $("notes").style.display = n ? "" : "none";  // hide the whole frame when there's no text
  }
  if ($("updated")) { $("updated").innerHTML = "Updated " + esc(DATA.updated); }
  checkStale();
}

function load() {
  var x = new XMLHttpRequest();
  x.open("GET", "data.json?t=" + new Date().getTime(), true);
  x.onreadystatechange = function () {
    if (x.readyState === 4 && x.status === 200) {
      try { DATA = JSON.parse(x.responseText); render(); } catch (e) {}
    }
  };
  x.send();
}

tick(); load();
setInterval(tick, 10000);
setInterval(load, 5 * 60 * 1000);
setInterval(pollLive, POLL_MS);

/* Tap anywhere once to hide the browser bars (browsers only allow full screen after a tap) */
(function () {
  var de = document.documentElement;
  var req = de.requestFullscreen || de.webkitRequestFullscreen || de.mozRequestFullScreen || de.msRequestFullscreen;
  if (!req) { return; }
  function go() {
    try { req.call(de); } catch (e) {}
  }
  function isFull() {
    return !!(document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement);
  }
  document.addEventListener("click", function () { if (!isFull()) { go(); } }, false);
  document.addEventListener("touchend", function () { if (!isFull()) { go(); } }, false);
})();
