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
      if ($("wdesc")) { $("wdesc").innerHTML = esc(w.desc) + " &middot; H " + w.hi + "&deg; L " + w.lo + "&deg;"; }
      if ($("days")) {
        var h = "";
        for (var i = 0; i < w.days.length; i++) {
          var x = w.days[i];
          h += "<div class='day'><b>" + x.day + "</b>" + x.icon + " " + x.hi + "&deg;/" + x.lo + "&deg;</div>";
        }
        $("days").innerHTML = h;
      }
    } else {
      $("temp").innerHTML = "--";
      if ($("wdesc")) { $("wdesc").innerHTML = "Weather unavailable"; }
    }
  }
  if ($("scores")) {
    var s = "";
    for (var j = 0; j < DATA.teams.length; j++) {
      var t = DATA.teams[j];
      s += "<div class='card" + (t.live ? " live" : "") + "'><div class='in'>" +
        "<div class='row'><span class='name'>" + esc(t.name) + "<span class='lg'>" + esc(t.league) + "</span></span>" +
        "<span class='head'>" + esc(t.head) + "</span></div>" +
        "<div class='sub'>" + esc(t.sub) + "</div></div></div>";
    }
    $("scores").innerHTML = s;
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
