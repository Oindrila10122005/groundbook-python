/* GroundBook frontend. Every screen reads the live API. The one table the browser holds itself is the
   rule table (RULES below), a copy of tests/rules.csv that tests/test_rules.py keeps equal to it. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); };
  var fmt = function (s) { return esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*(.+?)\*\*/g, "<b>$1</b>"); };
  var V = "/venues/deccan";
  var GROUNDS = null, TYPES = null, LAST_CLASH = [], GHOST = null, LAST = "";

  async function call(method, path, body) {
    var opts = { method: method, headers: {} };
    if (body !== undefined) { opts.headers["content-type"] = "application/json"; opts.body = JSON.stringify(body); }
    var r = await fetch(path, opts);
    var data = null;
    try { data = await r.json(); } catch (e) { data = null; }
    return { status: r.status, ok: r.ok, body: data, headers: { location: r.headers.get("location") } };
  }
  function refusal(p) {
    if (!p) return "<b>No answer</b>";
    var extra = [];
    if (p.clashes_with) extra.push("clashes with " + p.clashes_with.map(function (c) { return c.booking_id + " (held " + hm(c.ground_held_from) + "–" + hm(c.ground_held_to) + ")"; }).join(", "));
    if (p.opens) extra.push("the ground opens at " + p.opens + " and closes at " + p.closes);
    if (p.errors) extra.push(p.errors.map(function (e) { return e.field + ": " + e.message; }).join("; "));
    return "<b>" + esc(p.title || "Not available yet") + "</b><br>" + esc(p.detail || "") + (extra.length ? "<br>" + esc(extra.join(" · ")) : "") +
      "<br><small class='muted'>" + (p.status ? p.status + " · " + esc(p.type) : "this call is not built yet on this day") + "</small>";
  }
  function hm(iso) { return iso.slice(11, 16); }
  function dateOf(iso) { return iso.slice(0, 10); }
  function ts(date, hhmm) { return date + "T" + hhmm + ":00Z"; }
  function today() { return new Date().toISOString().slice(0, 10); }
  function addDays(date, n) { var d = new Date(date + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
  function weekday(date) { return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][new Date(date + "T00:00:00Z").getUTCDay()]; }
  function mins(hhmm) { return Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3, 5)); }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function minus(hhmm, m) { var v = mins(hhmm) - m; return pad(Math.floor(v / 60)) + ":" + pad(v % 60); }
  function plus(hhmm, m) { var v = mins(hhmm) + m; return pad(Math.floor(v / 60)) + ":" + pad(v % 60); }
  function nextSaturday() { var d = today(); while (weekday(d) !== "Sat") d = addDays(d, 1); return d; }

  function show(screen) {
    document.querySelectorAll(".screen").forEach(function (s) { s.classList.toggle("on", s.id === screen); });
    document.querySelectorAll("#nav button").forEach(function (b) { b.classList.toggle("on", b.dataset.screen === screen); });
    var load = { day: loadDay, book: loadBook, booking: function () { loadBooking($("bookingform").id.value.trim()); }, rules: loadRules, api: loadApi, runtime: loadRuntime };
    if (load[screen]) load[screen]();
  }
  $("nav").addEventListener("click", function (e) { var b = e.target.closest("button[data-screen]"); if (b) show(b.dataset.screen); });
  function openBooking(id) { $("bookingform").id.value = id; show("booking"); }

  async function reference() {
    if (GROUNDS && TYPES) return;
    GROUNDS = (await (await fetch(V + "/grounds")).json()).grounds;
    TYPES = (await (await fetch(V + "/event-types")).json()).event_types;
  }
  function typeOf(code) { return TYPES.filter(function (t) { return t.code === code; })[0]; }

  /* ---- the day: a strip per ground, blocks with their shadows; they are coloured by state, and a clash is marked ---- */
  $("daydate").value = nextSaturday();
  async function loadDay() {
    await reference();
    var date = $("daydate").value;
    $("legendrow").innerHTML = TYPES.map(function (t) { return "<span class='chip'><b>" + esc(t.code) + "</b> " + t.setup_minutes + " / " + t.teardown_minutes + "</span>"; }).join("");
    var days = await Promise.all(GROUNDS.map(function (g) { return call("GET", V + "/grounds/" + g.ground + "/day?date=" + date); }));
    if (!days[0].ok) { $("strips").innerHTML = "<p class='muted'>" + refusal(days[0].body) + "</p>"; return; }
    var opens = days[0].body.opens, closes = days[0].body.closes;
    var lo = mins(opens), hi = mins(closes), span = hi - lo;
    var left = function (m) { return ((m - lo) / span * 100).toFixed(2) + "%"; }, width = function (a, z) { return ((z - a) / span * 100).toFixed(2) + "%"; };
    $("dayline").textContent = weekday(date) + " · open " + opens + "–" + closes + (weekday(date) === "Sun" ? " (Sunday hours)" : "");
    var total = days.reduce(function (n, d) { return n + d.body.bookings.length; }, 0);
    $("strips").innerHTML = days.map(function (d, i) {
      var g = GROUNDS[i];
      var blocks = d.body.bookings.map(function (b) {
        var hf = mins(hm(b.ground_held_from)), ht = mins(hm(b.ground_held_to)), f = mins(hm(b.from)), t = mins(hm(b.to));
        var clash = LAST_CLASH.indexOf(b.booking_id) >= 0 ? " clash" : "";
        return "<div class='shadow " + b.state + clash + "' style='left:" + left(hf) + ";width:" + width(hf, ht) + "' title='held " + hm(b.ground_held_from) + "–" + hm(b.ground_held_to) + "'></div>" +
          "<div class='block " + b.state + clash + "' data-id='" + b.booking_id + "' style='left:" + left(f) + ";width:" + width(f, t) + "' title='" + b.booking_id + " " + b.event + " " + hm(b.from) + "–" + hm(b.to) + " (" + b.state + ")'><b>" + b.booking_id + "</b> " + esc(b.event) + " " + hm(b.from) + "–" + hm(b.to) + "</div>";
      }).join("");
      var ghost = "";
      if (GHOST && GHOST.ground === g.ground && GHOST.date === date) {
        ghost = "<div class='shadow ghost' style='left:" + left(mins(GHOST.held_from)) + ";width:" + width(mins(GHOST.held_from), mins(GHOST.held_to)) + "'></div>" +
          "<div class='block ghost' style='left:" + left(mins(GHOST.from)) + ";width:" + width(mins(GHOST.from), mins(GHOST.to)) + "'>refused</div>";
      }
      var ticks = ""; for (var h = Math.ceil(lo / 60); h * 60 <= hi; h += 2) ticks += "<span class='tick' style='left:" + ((h * 60 - lo) / span * 100).toFixed(2) + "%'>" + pad(h) + ":00</span>";
      return "<div class='striprow'><div class='striplbl'><b>" + esc(g.ground) + "</b><br><small>" + esc(g.name) + "</small></div><div class='strip'>" + ticks + blocks + ghost + "</div></div>";
    }).join("") + "<p class='muted'>" + total + " booking" + (total === 1 ? "" : "s") + " on " + date + (LAST_CLASH.length ? " · red: the two shadows the last refusal found touching" : "") + "</p>";
  }
  $("daydate").addEventListener("change", loadDay);
  $("dayprev").addEventListener("click", function () { $("daydate").value = addDays($("daydate").value, -1); loadDay(); });
  $("daynext").addEventListener("click", function () { $("daydate").value = addDays($("daydate").value, 1); loadDay(); });
  $("strips").addEventListener("click", function (e) { var t = e.target.closest(".block[data-id]"); if (t) openBooking(t.dataset.id); });

  /* ---- book: the form, the green and the red panel; the table of refusals ---- */
  async function loadBook() {
    await reference();
    if (!$("bookground").options.length) {
      $("bookground").innerHTML = GROUNDS.map(function (g) { return "<option value='" + g.ground + "'>" + g.ground + " — " + esc(g.name) + "</option>"; }).join("");
      $("bookevent").innerHTML = TYPES.map(function (t) { return "<option value='" + t.code + "'" + (t.code === "league" ? " selected" : "") + ">" + esc(t.name) + " (" + t.setup_minutes + " / " + t.teardown_minutes + ")</option>"; }).join("");
    }
    if (!$("bookform").date.value) $("bookform").date.value = $("daydate").value;
    var spec = await (await fetch("/openapi.json")).json();
    var seen = {}, rows = [];
    Object.keys(spec.paths).forEach(function (path) {
      Object.keys(spec.paths[path]).forEach(function (m) {
        var responses = spec.paths[path][m].responses || {};
        Object.keys(responses).forEach(function (status) {
          var content = responses[status].content && responses[status].content["application/problem+json"];
          if (!content || Number(status) >= 500) return;
          var examples = content.examples ? Object.keys(content.examples).map(function (k) { return content.examples[k].value; }) : content.example ? [content.example] : [];
          examples.forEach(function (ex) {
            var key = ex.type + "@" + m.toUpperCase() + " " + path;
            if (seen[key]) return; seen[key] = true;
            rows.push([Number(status), ex.type, ex.title, m.toUpperCase() + " " + path, Object.keys(ex).filter(function (k) { return ["type", "title", "status", "detail"].indexOf(k) < 0; }).join(", ")]);
          });
        });
      });
    });
    rows.sort(function (a, b) { return a[0] - b[0] || a[1].localeCompare(b[1]); });
    $("refusals").innerHTML = "<tr><th>Status</th><th>Type</th><th>Title</th><th>Where</th><th>Extra fields</th></tr>" + rows.map(function (r) { return "<tr><td>" + r[0] + "</td><td><code>" + esc(r[1]) + "</code></td><td>" + esc(r[2]) + "</td><td><code>" + esc(r[3]) + "</code></td><td>" + esc(r[4]) + "</td></tr>"; }).join("");
  }
  $("bookform").addEventListener("submit", async function (e) {
    e.preventDefault();
    var f = e.target, date = f.date.value;
    var body = { ground: f.ground.value, event: f.event.value, from: ts(date, f.from.value.trim()), to: ts(date, f.to.value.trim()), club: f.club.value.trim() };
    var r = await call("POST", "/bookings", body);
    $("bookok").hidden = !r.ok; $("bookno").hidden = r.ok;
    LAST_CLASH = []; GHOST = null;
    if (r.ok) {
      LAST = r.body.booking_id;
      $("bookok").innerHTML = "Booking <a href='#' id='openlast'><b>" + r.body.booking_id + "</b></a> · ground " + r.body.ground + " · " + esc(r.body.event) + " " + hm(r.body.from) + "–" + hm(r.body.to) + " on " + dateOf(r.body.from) +
        "<br>Ground held <b>" + hm(r.body.ground_held_from) + "–" + hm(r.body.ground_held_to) + "</b> · state <b>" + r.body.state + "</b> · hold until " + r.body.hold_until + "<br><small class='muted'>Location: " + esc(r.headers.location) + " — open the booking card to confirm or cancel it</small>";
      $("openlast").addEventListener("click", function (ev) { ev.preventDefault(); openBooking(LAST); });
      $("daydate").value = date;
    } else {
      $("bookno").innerHTML = refusal(r.body);
      if (r.body && r.body.clashes_with) {
        LAST_CLASH = r.body.clashes_with.map(function (c) { return c.booking_id; });
        var t = typeOf(body.event);
        GHOST = { ground: body.ground, date: date, from: f.from.value.trim(), to: f.to.value.trim(), held_from: minus(f.from.value.trim(), t.setup_minutes), held_to: plus(f.to.value.trim(), t.teardown_minutes) };
        $("daydate").value = date;
        $("bookno").innerHTML += "<br><small class='muted'>Open The day: the shadows that touch are marked in red, the refused request drawn hatched.</small>";
      }
    }
  });

  /* ---- the booking card: Confirm / Cancel, the Move form, the timeline ---- */
  var OPEN = null;
  function eventLine(ev) {
    var at = "<time>" + ev.at.slice(0, 16).replace("T", " ") + "</time>";
    if (ev.kind === "requested") return at + "requested " + hm(ev.from) + "–" + hm(ev.to) + " on " + dateOf(ev.from);
    if (ev.kind === "moved") return at + "moved " + hm(ev.previous_from) + "–" + hm(ev.previous_to) + " → " + hm(ev.from) + "–" + hm(ev.to) + " on " + dateOf(ev.from);
    if (ev.kind === "cancelled") return at + (ev.late ? "cancelled late — the slot had begun" : "cancelled");
    return at + esc(ev.kind);
  }
  async function loadBooking(id, keep) {
    if (!id) id = LAST;
    if (!id) { $("bookingcard").hidden = false; $("bookinghead").innerHTML = "<span class='muted'>No booking yet — request one on the Book screen, or click a block on The day.</span>"; $("bookingactions").hidden = true; $("timeline").innerHTML = ""; return; }
    $("bookingform").id.value = id;
    var r = await call("GET", "/bookings/" + encodeURIComponent(id));
    $("bookingcard").hidden = false;
    if (!r.ok) { $("bookinghead").innerHTML = refusal(r.body); $("bookingactions").hidden = true; $("timeline").innerHTML = ""; return; }
    var b = r.body; OPEN = b; LAST = b.booking_id;
    var late = (b.events || []).some(function (e) { return e.kind === "cancelled" && e.late; });
    $("bookinghead").innerHTML = "<b>" + b.booking_id + "</b> · ground " + b.ground + " · " + esc(b.event) + " · " + dateOf(b.from) + " " + hm(b.from) + "–" + hm(b.to) +
      " · state <b class='st-" + b.state + "'>" + (late ? "cancelled late" : b.state) + "</b><br>Ground held <b>" + hm(b.ground_held_from) + "–" + hm(b.ground_held_to) + "</b> (" + esc(b.event) + " buffers)";
    $("timeline").innerHTML = (b.events || []).map(function (ev) { return "<li>" + eventLine(ev) + "</li>"; }).join("");
    $("bookingactions").hidden = false;
    $("moveform").date.value = dateOf(b.from); $("moveform").from.value = plus(hm(b.from), 60); $("moveform").to.value = plus(hm(b.to), 60);
    if (!keep) { $("transout").hidden = true; $("moveout").hidden = true; }
  }
  $("bookingform").addEventListener("submit", function (e) { e.preventDefault(); loadBooking(e.target.id.value.trim()); });
  function transition(b) {
    if (b.confirmed_at) return "<b>" + b.booking_id + "</b> confirmed at " + b.confirmed_at + " — the clash check ran again and the ground is held.";
    return "<b>" + b.booking_id + "</b> cancelled at " + b.cancelled_at + (b.late ? " — <b>cancelled late</b>: the slot had begun." : " — the ground is free again.");
  }
  async function transitionOpen(action) {
    if (!OPEN) return;
    var r = await call("POST", "/bookings/" + OPEN.booking_id + "/" + action);
    $("transout").hidden = false; $("moveout").hidden = true;
    $("transout").innerHTML = r.ok ? "<div class='card ok'>" + transition(r.body) + "</div>" : "<div class='card no'>" + refusal(r.body) + "</div>";
    loadBooking(OPEN.booking_id, true);
  }
  $("confirmbtn").addEventListener("click", function () { transitionOpen("confirm"); });
  $("cancelbtn").addEventListener("click", function () { transitionOpen("cancel"); });
  $("moveform").addEventListener("submit", async function (e) {
    e.preventDefault();
    if (!OPEN) return;
    var f = e.target;
    var r = await call("POST", "/bookings/" + OPEN.booking_id + "/move", { from: ts(f.date.value, f.from.value.trim()), to: ts(f.date.value, f.to.value.trim()) });
    $("moveout").hidden = false; $("transout").hidden = true;
    LAST_CLASH = []; GHOST = null;
    if (r.ok) { $("moveout").innerHTML = "<div class='card ok'>Moved to " + hm(r.body.from) + "–" + hm(r.body.to) + " on " + dateOf(r.body.from) + ", held <b>" + hm(r.body.ground_held_from) + "–" + hm(r.body.ground_held_to) + "</b> at " + r.body.moved_at + ". The old interval is free; the block is in one place.</div>"; $("daydate").value = f.date.value; }
    else {
      $("moveout").innerHTML = "<div class='card no'>" + refusal(r.body) + (r.body && r.body.clashes_with ? "<br><small class='muted'>Refused before anything was erased — open The day: the block is still where it was.</small>" : "") + "</div>";
      if (r.body && r.body.clashes_with) { LAST_CLASH = r.body.clashes_with.map(function (c) { return c.booking_id; }); $("daydate").value = f.date.value; }
    }
    loadBooking(OPEN.booking_id, true);
  });

  /* ---- rule book: case, tag, given/then, then the expected status and type under uniform 40/30 and per type ---- */
  var RULES = [
    ["ok", "ok", "league 14:00–17:00 on an empty Saturday", 201, "", 201, ""],
    ["to_before_from", "interval", "league 17:00–14:00", 400, "/errors/bad-interval", 400, "/errors/bad-interval"],
    ["outside_hours", "interval", "league 05:00–07:00 (the ground opens at 06:00)", 400, "/errors/bad-interval", 400, "/errors/bad-interval"],
    ["shadow_outside_hours", "interval", "league 06:20–08:00: the 40 min setup would start at 05:40 (the answer names `opens` 06:00)", 400, "/errors/bad-interval", 400, "/errors/bad-interval"],
    ["malformed", "validation", "a request without `from`", 422, "/errors/validation", 422, "/errors/validation"],
    ["bad_day_date", "validation", "the day strip for 2026-13-40", 400, "/errors/validation", 400, "/errors/validation"],
    ["no_such_event_type", "event", "a 'concert'", 400, "/errors/no-such-event-type", 400, "/errors/no-such-event-type"],
    ["no_such_ground", "ground", "a request for ground Z", 404, "/errors/no-such-ground", 404, "/errors/no-such-ground"],
    ["no_such_venue", "venue", "the grounds of venue 'mumbai'", 404, "/errors/no-such-venue", 404, "/errors/no-such-venue"],
    ["overlap_left_buffer", "overlap", "league 14:00–16:00 (held from 13:20), then league 12:00–13:30 (held to 14:00)", 409, "/errors/overlap", 409, "/errors/overlap"],
    ["overlap_right_buffer", "overlap", "league 14:00–16:00 (held to 16:30), then league 16:00–18:00 (held from 15:20)", 409, "/errors/overlap", 409, "/errors/overlap"],
    ["back_to_back_just_fits", "overlap", "league 14:00–16:00 (held to 16:30), then league 17:10–19:00 (held from 16:30 exactly)", 201, "", 201, ""],
    ["confirm_ok", "confirm", "requested, clock before `from`, confirm", 200, "", 200, ""],
    ["confirm_started", "confirm", "clock 14:20 on the day, confirm", 409, "/errors/already-started", 409, "/errors/already-started"],
    ["confirm_twice", "confirm", "confirmed, confirm again", 409, "/errors/already-confirmed", 409, "/errors/already-confirmed"],
    ["cancel_over", "cancel", "clock 17:30, after `to`, cancel", 409, "/errors/already-over", 409, "/errors/already-over"],
    ["late_cancel", "cancel", "clock 14:20, after `from`, cancel (the answer says `late: true`)", 200, "", 200, ""],
    ["cancel_twice", "cancel", "cancelled, cancel again", 409, "/errors/already-cancelled", 409, "/errors/already-cancelled"],
    ["reconfirm_cancelled", "cancelled", "cancelled, then confirm", 409, "/errors/cancelled", 409, "/errors/cancelled"],
    ["no_such_booking", "booking", "confirm BK9999", 404, "/errors/no-such-booking", 404, "/errors/no-such-booking"],
    ["move_into_clash", "move", "league 14:00–17:00 and 18:30–20:30 (held from 17:50); move the first to 15:00–18:00 (held to 18:30)", 409, "/errors/overlap", 409, "/errors/overlap"],
    ["move_ok", "move", "league 14:00–17:00 moved to 15:00–18:00", 200, "", 200, ""],
    ["practice_after_league", "buffer", "league 14:00–16:00 (held to 16:30), then practice 17:00–18:00: held from 16:20 at 40 / 30, from 16:40 at 20 / 20", 409, "/errors/overlap", 201, ""],
    ["school_day_after_league", "buffer", "league 08:00–10:00 (held to 10:30), then school day 11:30–15:30: held from 10:50 at 40 / 30, from 09:30 at 120 / 120", 201, "", 409, "/errors/overlap"]
  ];
  function expected(status, type) { return status + (type ? " " + type.replace("/errors/", "") : ""); }
  function paintRuleTable() {
    var perType = $("rulemode").value === "per_type";
    $("ruletable").innerHTML = "<tr><th>Case</th><th>Tag</th><th>Given, then</th><th>Expected (" + esc($("rulemode").options[$("rulemode").selectedIndex].text) + ")</th></tr>" + RULES.map(function (r) {
      var moves = r[3] !== r[5] || r[4] !== r[6];
      return "<tr" + (moves ? " class='moves'" : "") + "><td><code>" + r[0] + "</code></td><td>" + r[1] + "</td><td>" + fmt(r[2]) + "</td><td><code>" + esc(perType ? expected(r[5], r[6]) : expected(r[3], r[4])) + "</code></td></tr>";
    }).join("");
  }
  $("rulemode").addEventListener("change", paintRuleTable);
  async function loadRules() {
    var r = await call("GET", "/settings");
    if (r.ok) {
      var s = r.body;
      $("settings").innerHTML = "<dt>Hold</dt><dd>" + s.hold_hours + " hours — a requested slot holds the ground this long; after <code>HOLD_HOURS=" + s.hold_hours + "</code> the request no longer holds the ground</dd>" +
        "<dt>Intervals</dt><dd>half-open [from, to), 30 minutes to 12 hours, one date, never the past; the shadow must lie inside the ground's hours for that weekday (Sunday has its own)</dd>" +
        "<dt>The life of a booking</dt><dd>requested → confirmed (before it starts; the clash check runs again) → cancelled (before it ends; late once it has begun) — or moved at any point before it starts, the whole new shadow re-checked</dd>";
      $("buffers").innerHTML = "<tr><th>Event type</th><th>Setup</th><th>Teardown</th><th>A 14:00–16:00 booking is held</th></tr>" + Object.keys(s.buffers).map(function (code) {
        var b = s.buffers[code];
        return "<tr><td><code>" + esc(code) + "</code></td><td>" + b[0] + " min</td><td>" + b[1] + " min</td><td>" + minus("14:00", b[0]) + "–" + plus("16:00", b[1]) + "</td></tr>";
      }).join("");
      var uniform = Object.keys(s.buffers).every(function (c) { return s.buffers[c][0] === 40 && s.buffers[c][1] === 30; });
      $("rulemode").value = uniform ? "uniform" : "per_type";
    }
    paintRuleTable();
  }

  /* ---- API: every call from the live spec; Send shows its answer right here ---- */
  function samples() {
    var d = $("daydate").value || nextSaturday();
    return { "POST /bookings": { ground: "A", event: "league", from: ts(d, "14:00"), to: ts(d, "17:00"), club: "Ambedkar Nagar CC" },
             "POST /bookings/{booking_id}/move": { from: ts(d, "15:00"), to: ts(d, "18:00") } };
  }
  function samplePath(path) { return path.replace("{venue}", "deccan").replace("{ground}", "A").replace("{booking_id}", LAST || "BK0001") + (path.slice(-4) === "/day" ? "?date=" + ($("daydate").value || nextSaturday()) : ""); }
  async function loadApi() {
    var r = await call("GET", "/openapi.json");
    if (!r.ok) return;
    var rows = [];
    Object.keys(r.body.paths).forEach(function (path) {
      Object.keys(r.body.paths[path]).forEach(function (m) {
        var op = r.body.paths[path][m];
        rows.push("<tr><td><code>" + m.toUpperCase() + " " + esc(path) + "</code></td><td>" + esc(op.summary || "") + "</td><td>" + Object.keys(op.responses).join(" · ") +
          "</td><td><button type='button' class='send' data-m='" + m.toUpperCase() + "' data-p='" + esc(path) + "'>Send</button></td></tr>");
      });
    });
    $("endpoints").innerHTML = "<tr><th>Call</th><th>What it does</th><th>Answers</th><th></th></tr>" + rows.join("");
  }
  $("endpoints").addEventListener("click", async function (e) {
    var b = e.target.closest("button.send"); if (!b) return;
    var path = samplePath(b.dataset.p), body = samples()[b.dataset.m + " " + b.dataset.p];
    var r = await call(b.dataset.m, path, body);
    if (r.ok && r.body && r.body.booking_id) LAST = r.body.booking_id;
    $("apiout").hidden = false;
    $("apiout").textContent = b.dataset.m + " " + path + (body ? "\n" + JSON.stringify(body) : "") + "\n\nHTTP " + r.status + (r.headers.location ? "\nlocation: " + r.headers.location : "") + "\n" + JSON.stringify(r.body, null, 2);
  });

  /* ---- runtime: health and the image; Saturday before and after a restart ---- */
  async function loadRuntime() {
    var r = await call("GET", "/healthz");
    $("healthdot").className = "dot " + (r.ok ? "up" : "down");
    $("healthtext").textContent = r.ok ? "up — GET /healthz " + JSON.stringify(r.body) : "down";
    var s = await call("GET", "/settings");
    if (s.ok) $("runtimeline").textContent = "image groundbook (python:3.12-slim) · hold " + s.body.hold_hours + " h and " + Object.keys(s.body.buffers).length + " event types with their buffers, from GET /settings";
    if (!$("restartdate").value) $("restartdate").value = nextSaturday();
  }
  var SNAPSHOT = "groundbook.saturday";
  async function saturday(date) {
    await reference();
    var out = {};
    for (var i = 0; i < GROUNDS.length; i++) {
      var r = await call("GET", V + "/grounds/" + GROUNDS[i].ground + "/day?date=" + date);
      if (!r.ok) throw new Error(r.body ? r.body.title : "HTTP " + r.status);
      out[GROUNDS[i].ground] = r.body.bookings;
    }
    return out;
  }
  function count(grounds) { return Object.keys(grounds).reduce(function (n, g) { return n + grounds[g].length; }, 0); }
  function restartSay(cls, html) { $("restartout").hidden = false; $("restartout").innerHTML = "<div class='card " + cls + "'>" + html + "</div>"; }
  $("beforebtn").addEventListener("click", async function () {
    var date = $("restartdate").value, grounds;
    try { grounds = await saturday(date); } catch (e) { restartSay("no", "Could not read " + esc(date) + ": " + esc(e.message)); return; }
    var kept = false;
    try { localStorage.setItem(SNAPSHOT, JSON.stringify({ date: date, grounds: grounds })); kept = true; } catch (e) { kept = false; }
    restartSay(kept ? "ok" : "no", kept ? "Kept " + count(grounds) + " booking(s) on " + Object.keys(grounds).length + " grounds for " + esc(date) + ". Now run the two commands, then press After restart."
      : "This browser would not keep the copy (storage is blocked); the comparison needs it.");
  });
  $("afterbtn").addEventListener("click", async function () {
    var snap = null;
    try { snap = JSON.parse(localStorage.getItem(SNAPSHOT) || "null"); } catch (e) { snap = null; }
    if (!snap) { restartSay("no", "No copy kept yet — press Before restart first."); return; }
    var now;
    try { now = await saturday(snap.date); } catch (e) { restartSay("no", "Could not read " + esc(snap.date) + ": " + esc(e.message)); return; }
    var diffs = [];
    Object.keys(snap.grounds).concat(Object.keys(now)).filter(function (g, i, all) { return all.indexOf(g) === i; }).forEach(function (g) {
      var before = {}, after = {};
      (snap.grounds[g] || []).forEach(function (b) { before[b.booking_id] = b; });
      (now[g] || []).forEach(function (b) { after[b.booking_id] = b; });
      Object.keys(before).forEach(function (id) {
        if (!after[id]) { diffs.push("ground " + g + ": " + id + " is gone"); return; }
        Object.keys(before[id]).forEach(function (k) { if (before[id][k] !== after[id][k]) diffs.push("ground " + g + ": " + id + " " + k + " " + before[id][k] + " → " + after[id][k]); });
      });
      Object.keys(after).forEach(function (id) { if (!before[id]) diffs.push("ground " + g + ": " + id + " is new"); });
    });
    restartSay(diffs.length ? "no" : "ok", diffs.length ? "<b>" + diffs.length + " difference(s)</b> on " + esc(snap.date) + "<ul>" + diffs.map(function (d) { return "<li>" + esc(d) + "</li>"; }).join("") + "</ul>"
      : "<b>unchanged</b> — " + count(now) + " booking(s) on " + esc(snap.date) + ", every one exactly as before the restart.");
  });

  /* ---- walkthrough: the tickets, one at a time, on top of the screens they built ---- */
  var WALK = null, step = 0;
  var TAGS = { day: ["B-01"], book: ["B-02", "B-04"], booking: ["B-03", "B-05", "B-06"], rules: ["B-08"], api: ["B-07"], runtime: ["B-09", "B-10"] };
  var SCREEN_NAMES = { day: "The day", book: "Book", booking: "Booking", rules: "Rule book", api: "API", runtime: "Runtime" };
  function list(items) { return "<ul>" + items.map(function (s) { return "<li>" + fmt(s) + "</li>"; }).join("") + "</ul>"; }
  function acTable(rows) {
    return "<table class='tbl ac'><tr><th></th><th>given</th><th>when</th><th>then</th></tr>" + rows.map(function (r, i) {
      return "<tr><td>" + (i + 1) + "</td><td>" + fmt(r[0]) + "</td><td>" + fmt(r[1]) + "</td><td>" + fmt(r[2]) + "</td></tr>";
    }).join("") + "</table>";
  }
  function endpoint(e) {
    var h = "<div class='ep'><div class='sig'><b>" + e.m + "</b> " + esc(e.p) + "</div>";
    if (e.q) h += "<div class='muted'>? " + fmt(e.q) + "</div>";
    if (e.req) h += "<div class='muted'>request</div><pre>" + esc(JSON.stringify(e.req, null, 2)) + "</pre>";
    if (e.res) h += "<div class='muted'>response</div><pre>" + esc(JSON.stringify(e.res, null, 2)) + "</pre>";
    if (e.codes.length) h += "<table class='tbl ac'><tr><th>status</th><th>type</th><th>when</th></tr>" + e.codes.map(function (c) {
      return "<tr><td class='st " + (/^2/.test(c[0]) ? "ok" : "no") + "'>" + esc(c[0]) + "</td><td><code>" + esc(c[1]) + "</code></td><td>" + fmt(c[2]) + "</td></tr>";
    }).join("") + "</table>";
    return h + "</div>";
  }
  function paintStep() {
    var s = WALK.steps[step];
    $("walkpos").textContent = "Ticket " + (step + 1) + " of " + WALK.steps.length + " · " + WALK.level;
    $("walkprev").disabled = step === 0; $("walknext").disabled = step === WALK.steps.length - 1;
    $("walkid").textContent = s.id; $("walktitle").textContent = s.title; $("walkscene").innerHTML = fmt(s.scene);
    $("walkus").innerHTML = "As a <b>" + esc(s.story.as) + "</b>, I want to " + fmt(s.story.want) + ", so that " + fmt(s.story.so) + ".";
    $("walktry").innerHTML = "<div class='lbl'>Try it — " + SCREEN_NAMES[s.try.screen] + " screen</div><p>" + fmt(s.try.do) + "</p>" +
      "<div class='lbl'>What will happen</div><p>" + fmt(s.try.see) + "</p><button type='button' id='walkgo'>Go to " + SCREEN_NAMES[s.try.screen] + "</button>";
    $("walkgo").addEventListener("click", function () { show(s.try.screen); document.getElementById(s.try.screen).scrollIntoView({ behavior: "smooth", block: "start" }); });
    $("walkbuild").innerHTML = fmt(s.build); $("walkfollows").innerHTML = fmt(s.follows);
    $("walkcontract").innerHTML = "<p>" + fmt(s.summary) + "</p>" +
      (s.endpoints.length ? s.endpoints.map(endpoint).join("") : "<p class='muted'>No HTTP surface changes on this day — the work is in the code, the database or the container.</p>") +
      "<div class='muted' style='margin-top:8px'>What is stored</div>" + list(s.data) + "<div class='muted' style='margin-top:8px'>Rules the backend enforces</div>" + list(s.rules);
    $("walkacuser").innerHTML = acTable(s.ac_user); $("walkacapi").innerHTML = acTable(s.ac_api); $("walkdone").innerHTML = list(s.done);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  async function openWalk(id) {
    if (!WALK) WALK = await (await fetch("/static/walkthrough.json")).json();
    if (id) step = Math.max(0, WALK.steps.findIndex(function (s) { return s.id === id; }));
    $("walk").hidden = false; $("walkbtn").classList.add("on"); paintStep();
  }
  $("walkbtn").addEventListener("click", function () { if ($("walk").hidden) openWalk(); else { $("walk").hidden = true; $("walkbtn").classList.remove("on"); } });
  $("walkclose").addEventListener("click", function () { $("walk").hidden = true; $("walkbtn").classList.remove("on"); });
  $("walkprev").addEventListener("click", function () { if (step > 0) { step--; paintStep(); } });
  $("walknext").addEventListener("click", function () { if (step < WALK.steps.length - 1) { step++; paintStep(); } });
  Object.keys(TAGS).forEach(function (screen) {
    var h2 = document.querySelector("#" + screen + " h2");
    TAGS[screen].forEach(function (id) { h2.insertAdjacentHTML("beforeend", "<span class='tag' data-step='" + id + "' title='Open this ticket in the walkthrough'>" + id + "</span>"); });
  });
  document.addEventListener("click", function (e) { var t = e.target.closest(".tag"); if (t) openWalk(t.dataset.step); });

  show("day");
})();
