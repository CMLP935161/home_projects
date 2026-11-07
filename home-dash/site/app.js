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
    $("date").innerHTML = days[d.getDay()] + ", " + mons[d.getMonth()] + " " + d.getDate();
  }
  checkStale();
}

function checkStale() {
  if (!DATA || !$("stale")) { return; }
  var ageMin = (new Date().getTime() / 1000 - DATA.updated_epoch) / 60;
  $("stale").innerHTML = ageMin > 120 ? "Data is " + Math.round(ageMin / 60) + "h old" : "";
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
  if ($("scores")) {
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
