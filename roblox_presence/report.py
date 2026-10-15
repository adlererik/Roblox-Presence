"""Private, self-contained fourteen-day presence report. No network or credentials."""

import hashlib
import html
import json
import os
import pwd
import secrets
import sqlite3
import stat
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import ConfigError
from .roblox import clean_text
from .state import preserve_sqlite_owner


def server_zone():
    """Use the host's actual timezone rules, including historical DST offsets."""
    override = os.environ.get("TZ")
    if override:
        try:
            return ZoneInfo(override.removeprefix(":")), override.removeprefix(":")
        except (ZoneInfoNotFoundError, ValueError):
            raise ConfigError("TZ must be an installed IANA timezone such as Europe/Paris or UTC") from None
    try:
        path = Path("/etc/localtime")
        resolved = str(path.resolve())
        label = resolved.split("/zoneinfo/", 1)[-1] if "/zoneinfo/" in resolved else "server local time"
        with path.open("rb") as stream:
            return ZoneInfo.from_file(stream, key=label), label
    except (OSError, ValueError):
        raise ConfigError("Server timezone is unavailable; configure the host clock or set TZ to its IANA timezone") from None


def stamp(value, zone):
    return datetime.fromtimestamp(value, zone).strftime("%a %d %b %Y, %H:%M:%S %Z (UTC%z)")


def duration(seconds):
    minutes = max(0, int(seconds) // 60)
    return f"{minutes // 60}h {minutes % 60:02d}m" if minutes >= 60 else f"{minutes}m"


def snapshot(config, now, zone):
    start_date = datetime.fromtimestamp(now, zone).date() - timedelta(days=13)
    start = datetime.combine(start_date, time(), zone).timestamp()
    path = config.state_dir / "state.sqlite3"
    if not path.is_file() or path.is_symlink():
        raise ConfigError("No recorded history yet. Start the updated monitor first; old activity cannot be recovered")
    owner = path.stat()
    try:
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        with db:
            db.execute("BEGIN")
            if db.execute("PRAGMA user_version").fetchone()[0] != 2:
                raise ConfigError("History needs monitor version 0.2.0 or later; upgrade this monitor first")
            row = db.execute("SELECT details,last_success,last_error FROM monitor WHERE scope=?", (config.scope,)).fetchone()
            rows = [dict(r) for r in db.execute(
                "SELECT observed_at,kind,event,event_at FROM history WHERE scope=? AND observed_at>=? "
                "AND observed_at<=? ORDER BY observed_at,id", (config.scope, start, now))]
        return {"start": start, "rows": rows, "details": json.loads(row["details"]) if row else {}}
    except sqlite3.Error:
        raise ConfigError("Cannot read this monitor's history; check access without changing state permissions") from None
    finally:
        if 'db' in locals():
            db.close()
        preserve_sqlite_owner(path, owner)


def intervals(rows, now, maximum_gap):
    """Known spans end at the last valid check when a check fails or polling stops."""
    spans = []
    for index, row in enumerate(rows):
        start = row["observed_at"]
        if index + 1 >= len(rows):
            break  # Do not extrapolate beyond the last recorded observation.
        following = rows[index + 1]
        end = min(following["observed_at"], now)
        kind = row["kind"]
        if kind not in ("online", "offline") or following["kind"] not in ("online", "offline") or end - start > maximum_gap:
            continue
        if end <= start:
            continue
        if spans and spans[-1][2] == kind and spans[-1][1] == start:
            spans[-1] = (spans[-1][0], end, kind)
        else:
            spans.append((start, end, kind))
    return spans


STYLE = """
:root{color-scheme:light;--ink:#152c36;--muted:#526974;--line:#dae3e4;--online:#087f72;--offline:#dce6e8;--paper:#f5f6f1}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 system-ui,-apple-system,sans-serif}main{max-width:1100px;margin:auto;padding:36px 28px 50px}header{display:flex;justify-content:space-between;gap:24px;align-items:start}.eyebrow{text-transform:uppercase;letter-spacing:.16em;font-size:11px;font-weight:750;color:var(--online)}h1{font-size:34px;line-height:1.15;margin:8px 0 12px;letter-spacing:-.04em}h2{font-size:19px;margin:0}p{margin:6px 0;color:var(--muted)}.pill{background:#e2efeb;border:1px solid #a9d1c5;color:#076455;border-radius:22px;padding:9px 14px;font-size:13px;white-space:nowrap}.pill.offline{background:#edf1f2;border-color:#d5dee1;color:#425d6b}.pill.unknown,.pill.pending{background:#fff0d9;border-color:#edce9d;color:#805115}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:28px 0 20px}.card,.panel{background:#fff;border:1px solid var(--line);border-radius:15px}.card{padding:18px 22px}.value{display:block;font-size:27px;font-weight:700;letter-spacing:-.04em}.label{color:var(--muted);font-size:12px}.panel{padding:23px 24px;margin-top:20px}.panelhead{display:flex;gap:15px;justify-content:space-between;align-items:start;margin-bottom:22px}.legend{display:flex;gap:15px;flex-wrap:wrap;font-size:12px;color:var(--muted)}.key{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px;background:var(--offline)}.key.online{background:var(--online)}.key.unknown{background:repeating-linear-gradient(135deg,#d9ded8 0 2px,#f4f5f0 2px 5px)}.scroll{overflow-x:auto}.timeline{min-width:620px}.axis,.day{display:grid;grid-template-columns:113px 1fr 83px;gap:12px;align-items:center}.axis{margin-bottom:9px;font-size:11px;color:var(--muted)}.hours{position:relative;height:18px}.hours span{position:absolute;transform:translateX(-50%)}.hours span:first-child{transform:none}.hours span:last-child{transform:translateX(-100%)}.day{padding:5px 0}.daylabel{border:0;background:none;color:var(--ink);font:inherit;font-size:12px;text-align:left;cursor:pointer;padding:5px 4px;border-radius:5px}.daylabel:hover,.daylabel[aria-pressed=true]{background:#e2efeb;color:#076455}.track{height:23px;position:relative;border:1px solid #e1e5df;overflow:hidden;border-radius:5px;background:repeating-linear-gradient(135deg,#e0e4dc 0 1px,#f3f5ef 1px 5px)}.span{position:absolute;top:0;bottom:0;background:var(--online);min-width:2px}.span.offline{background:var(--offline);min-width:0}.future{position:absolute;top:0;bottom:0;background:#fff}.total{text-align:right;font-size:12px;font-variant-numeric:tabular-nums;color:var(--muted)}.note{font-size:12px;margin-top:16px;max-width:880px}.empty{padding:25px 0;color:var(--muted)}button:focus-visible,a:focus-visible{outline:3px solid #cb7e2b;outline-offset:3px}.reset{border:1px solid var(--line);border-radius:8px;background:white;padding:7px 12px;color:var(--ink);cursor:pointer}.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600;padding:12px 10px;border-bottom:1px solid var(--line)}td{padding:13px 10px;border-bottom:1px solid #edf0ea;font-variant-numeric:tabular-nums;white-space:nowrap}td:last-child{white-space:normal;min-width:200px;color:var(--muted)}.event{display:inline-block;border-radius:5px;padding:3px 8px;background:#e2efeb;color:#076455;font-weight:650}.event.off{background:#edf1f2;color:#425d6b}.footer{display:flex;justify-content:space-between;gap:20px;font-size:11px;margin-top:21px;color:var(--muted)}[hidden]{display:none!important}@media(max-width:650px){main{padding:24px 15px}h1{font-size:29px}header{display:block}.pill{display:inline-block;margin-top:12px}.cards{gap:8px}.card{padding:13px 11px}.value{font-size:23px}.panel{padding:18px 14px}.panelhead{display:block}.legend{margin-top:12px}.footer{display:block}.footer span{display:block;margin-top:6px}.timeline{min-width:0}.axis,.day{grid-template-columns:80px minmax(0,1fr) 42px;gap:6px}.daylabel{font-size:10px;padding:5px 0}.total{font-size:10px}.axis{font-size:9px}.tablewrap table,.tablewrap tbody,.tablewrap tr,.tablewrap td{display:block}.tablewrap thead{position:absolute;width:1px;height:1px;overflow:hidden}.tablewrap tr{padding:12px 0;border-bottom:1px solid var(--line)}.tablewrap td{padding:3px 0;border:0;white-space:normal;min-width:0}.tablewrap td:nth-child(2){font-weight:650}.tablewrap td:last-child{font-size:12px}}@media print{body{background:white}main{max-width:none;padding:0}.reset{display:none}.panel{break-inside:avoid}.tablewrap{overflow:visible}tr[hidden]{display:table-row!important}}
"""
SCRIPT = """
const days=[...document.querySelectorAll('.daylabel')];
const rows=[...document.querySelectorAll('tbody tr[data-day]')];
function select(day){days.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.day===day)));rows.forEach(r=>r.hidden=Boolean(day&&r.dataset.day!==day));document.getElementById('filter').textContent=day?'Showing '+day:'All 14 days';document.getElementById('noevents').hidden=!day||rows.some(r=>!r.hidden);}
days.forEach(b=>b.addEventListener('click',()=>select(b.getAttribute('aria-pressed')==='true'?'':b.dataset.day)));
document.getElementById('reset').addEventListener('click',()=>select(''));
"""


def render(data, now, zone, zone_name, poll_seconds=15):
    esc = lambda value: html.escape(str(value), quote=True)
    rows = data["rows"]
    spans = intervals(rows, now, max(60, poll_seconds * 3))
    details = data.get("details") or {}
    display, username = clean_text(details.get("display_name"), 80), clean_text(details.get("username"), 40)
    name = f"{display} (@{username})" if display and username else display or ("@" + username if username else "Monitored connection")
    first_date = datetime.fromtimestamp(now, zone).date() - timedelta(days=13)
    online_seconds = sum(b - a for a, b, k in spans if k == "online")
    known_seconds = sum(b - a for a, b, k in spans)
    window = now - datetime.combine(first_date, time(), zone).timestamp()
    events = [r for r in rows if r["event"]]
    seen_online = sum(r["event"] in ("online", "first_online") for r in events)
    recent = rows[-1] if rows else None
    current = recent["kind"] if recent and 0 <= now - recent["observed_at"] <= max(60, poll_seconds * 3) else "unknown"
    badge = {"online": "● Online at last check", "offline": "○ Offline at last check"}.get(current, "? Status unavailable")
    days = []
    for offset in range(13, -1, -1):
        date = first_date + timedelta(days=offset)
        begin = datetime.combine(date, time(), zone).timestamp()
        end = datetime.combine(date + timedelta(days=1), time(), zone).timestamp()
        length = end - begin
        parts, total = [], 0
        for a, b, kind in spans:
            left, right = max(a, begin), min(b, end, now)
            if right <= left:
                continue
            if kind == "online":
                total += right - left
            title = f"{kind.title()}: {stamp(left, zone)} → {stamp(right, zone)}"
            parts.append(f'<div class="span {kind}" style="left:{100*(left-begin)/length:.5f}%;width:{100*(right-left)/length:.5f}%" title="{esc(title)}"></div>')
        if end > now:
            left = max(0, (now - begin) / length * 100)
            parts.append(f'<div class="future" style="left:{left:.5f}%;right:0" title="Later today"></div>')
        ticks = []
        for hour in (0, 6, 12, 18, 24):
            tick = end if hour == 24 else datetime.combine(date, time(hour), zone).timestamp()
            ticks.append(f'<span style="left:{100*(tick-begin)/length:.5f}%">{hour:02d}:00</span>')
        label = ("Today · " if offset == 13 else "") + date.strftime("%a %d %b")
        dst = " · clock change" if length != 86400 else ""
        days.append(f'<div class="axis"><span></span><div class="hours">{"".join(ticks)}</div><span></span></div>' if length != 86400 else "")
        days.append(f'<div class="day"><button class="daylabel" data-day="{date.isoformat()}" aria-pressed="false" title="Show events for this day{dst}">{esc(label)}{(" *" if dst else "")}</button><div class="track" aria-label="{esc(label+dst)}">{"".join(parts)}</div><span class="total">{duration(total)}</span></div>')
    table = []
    for row in reversed(events):
        at = row["event_at"] if row["event_at"] is not None else row["observed_at"]
        if datetime.fromtimestamp(at, zone).date() < first_date:
            continue
        event = row["event"]
        online = event in ("online", "first_online")
        label = {"online": "Seen online", "offline": "Seen offline", "first_online": "First seen online", "first_offline": "First seen offline"}[event]
        note = "First recorded state; actual session start is unknown." if event.startswith("first_") else "Detected by a presence check; actual change occurred between checks."
        if event == "offline":
            note = "First offline check. Confirmed " + stamp(row["observed_at"], zone) + "."
        table.append(f'<tr data-day="{datetime.fromtimestamp(at, zone).date().isoformat()}"><td><span class="event {"" if online else "off"}">{label}</span></td><td>{esc(stamp(at, zone))}</td><td>{esc(note)}</td></tr>')
    empty = '<p class="empty">No recorded activity yet. Keep the updated monitor running; earlier activity cannot be recovered.</p>' if not rows else ""
    first = stamp(rows[0]["observed_at"], zone) if rows else "Not recorded yet"
    script_hash = __import__('base64').b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-{script_hash}'; base-uri 'none'; form-action 'none'; connect-src 'none'"><title>Roblox Presence · 14 days</title><style>{STYLE}</style></head><body><main>
<header><div><div class="eyebrow">Roblox Presence / Activity overview</div><h1>The past 14 days</h1><p>{esc(name)}</p><p>{esc(first_date.strftime('%d %b'))} – {esc(datetime.fromtimestamp(now, zone).strftime('%d %b %Y'))} · Server time: <strong>{esc(zone_name)}</strong></p></div><span class="pill {esc(current)}">{badge}</span></header>
<section class="cards" aria-label="Activity summary"><div class="card"><span class="value">{duration(online_seconds)}</span><span class="label">Observed online time</span></div><div class="card"><span class="value">{seen_online}</span><span class="label">Online appearances</span></div><div class="card"><span class="value">{round(100*known_seconds/window) if window else 0}%</span><span class="label">Window with recorded checks</span></div></section>
<section class="panel"><div class="panelhead"><div><h2>When were they online?</h2><p class="label">One row per day · Select a date to filter the times below</p></div><div class="legend"><span><i class="key online"></i>Online</span><span><i class="key"></i>Offline</span><span><i class="key unknown"></i>No reliable checks</span></div></div>{empty}<div class="scroll"><div class="timeline"><div class="axis"><span>Date</span><div class="hours"><span style="left:0">00:00</span><span style="left:25%">06:00</span><span style="left:50%">12:00</span><span style="left:75%">18:00</span><span style="left:100%">24:00</span></div><span style="text-align:right">Online time</span></div>{''.join(days)}</div></div><p class="note">Green includes online, in a game and Studio. Stripes mean missing checks, an unconfirmed offline result, or time before recording began. White is later today. Bars end at the last reliable check. * Clock-change days have their own time axis.</p></section>
<section class="panel"><div class="panelhead"><div><h2>Detected login &amp; logout times</h2><p class="label" id="filter" aria-live="polite">All 14 days</p></div><button class="reset" id="reset">Show all days</button></div><div class="tablewrap"><table><thead><tr><th>What happened</th><th>Server clock</th><th>How to read it</th></tr></thead><tbody>{''.join(table)}</tbody></table></div><p id="noevents" class="empty" hidden>No state changes recorded on this date.</p>{('<p class="empty">No state changes recorded in this window.</p>' if not events else '')}<p class="note">These are observation times, not Roblox login/logout records. Checks normally run every {poll_seconds} seconds; Roblox reporting delays and outages can increase uncertainty. Offline changes require consecutive successful checks. Activity during gaps is unknown, and a session across a gap may contain unobserved logins or logouts. All times use the server timezone, even when this file is opened on a phone elsewhere.</p></section>
<div class="footer"><span>Private report · Keep this file out of public repositories</span><span>Generated {esc(stamp(now, zone))}<br>First check in this window: {esc(first)}</span></div></main><script>{SCRIPT}</script></body></html>'''


def export_report(content, output=None):
    """Atomic mode-0600 export, owned by the person invoking sudo when applicable."""
    uid, gid = os.geteuid(), os.getegid()
    if uid == 0 and os.environ.get("SUDO_UID", "").isdigit():
        uid = int(os.environ["SUDO_UID"])
        gid = pwd.getpwuid(uid).pw_gid
    home = Path(pwd.getpwuid(uid).pw_dir)
    path = Path(output).expanduser().absolute() if output else home / "roblox-presence.html"
    if path.suffix.lower() != ".html":
        raise ConfigError("Choose an output filename ending in .html")
    parent = path.parent.resolve()
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".roblox-report-" + secrets.token_hex(12)
    try:
        info = os.fstat(directory)
        if info.st_uid != uid or info.st_mode & 0o022:
            raise ConfigError("Choose a private output folder owned by the receiving user (normally their home folder)")
        try:
            existing = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing and (not stat.S_ISREG(existing.st_mode) or existing.st_uid != uid or existing.st_nlink != 1):
            raise ConfigError("Report output already exists with an unsafe type or owner; choose another .html filename")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            if os.geteuid() == 0:
                os.fchown(stream.fileno(), uid, gid)
            os.fsync(stream.fileno())
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(directory)
    return parent / path.name
