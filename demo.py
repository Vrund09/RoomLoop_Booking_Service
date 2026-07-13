import json
import urllib.request
import urllib.error
import sys

BASE_URL = "http://localhost:8000"

def pp(data):
    print(json.dumps(data, indent=2))

def say(title):
    print(f"\n== {title} ==")

def make_request(path, method="GET", data=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    req_data = json.dumps(data).encode("utf-8") if data is not None else None
    
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            res_data = response.read().decode("utf-8")
            return json.loads(res_data) if res_data else {}
    except urllib.error.HTTPError as e:
        res_data = e.read().decode("utf-8")
        try:
            return json.loads(res_data)
        except Exception:
            return {"error": res_data or str(e)}
    except Exception as e:
        return {"error": str(e)}

def main():
    # 1. List rooms
    say("1. List rooms (C2 contract: bare array of id/name/capacity)")
    pp(make_request("/rooms"))

    # 2. Book Cinder (room 9, Denver) — single booking
    say("2. Book Cinder (room 9, Denver) — single booking")
    pp(make_request("/bookings", "POST", {
        "room_id": 9,
        "user": "alice@corp.com",
        "start": "2026-08-03T09:00:00",
        "end": "2026-08-03T10:00:00"
    }))

    # 3. Denver weekly series 09:00 crossing the 2027-03-14 spring-forward
    say("3. Denver weekly series 09:00 crossing the 2027-03-14 spring-forward")
    print("   Every start MUST stay at T09:00:00 — this is the Denver 'hour off' fix.")
    pp(make_request("/bookings/recurring", "POST", {
        "room_id": 9,
        "user": "bob@corp.com",
        "start": "2027-03-01T09:00:00",
        "end": "2027-03-01T10:00:00",
        "repeat_until": "2027-03-22"
    }))

    # 3b. Denver weekly 02:30 crossing 2027-03-14 — the gap instance is skipped
    say("3b. Denver weekly 02:30 crossing 2027-03-14 — the gap instance is skipped")
    print("   2027-03-14T02:30:00 does not exist -> reason: nonexistent_local_time.")
    pp(make_request("/bookings/recurring", "POST", {
        "room_id": 9,
        "user": "bob@corp.com",
        "start": "2027-03-07T02:30:00",
        "end": "2027-03-07T03:30:00",
        "repeat_until": "2027-03-21"
    }))

    # 4. Partially-conflicting series — pre-book one week, then create the series
    say("4. Partially-conflicting series — pre-book one week, then create the series")
    make_request("/bookings", "POST", {
        "room_id": 4,
        "user": "eve@corp.com",
        "start": "2026-09-14T09:30:00",
        "end": "2026-09-14T10:30:00"
    })
    print("   Series below overlaps the 2026-09-14 pre-booking -> that week is skipped.")
    series_res = make_request("/bookings/recurring", "POST", {
        "room_id": 4,
        "user": "bob@corp.com",
        "start": "2026-09-07T09:00:00",
        "end": "2026-09-07T10:00:00",
        "repeat_until": "2026-09-28"
    })
    pp(series_res)
    series_id = series_res.get("series_id")

    # 5. Back-to-back bookings are NOT a conflict (strict overlap)
    say("5. Back-to-back bookings are NOT a conflict (strict overlap)")
    pp(make_request("/bookings", "POST", {
        "room_id": 3,
        "user": "carol@corp.com",
        "start": "2026-08-10T10:00:00",
        "end": "2026-08-10T11:00:00"
    }))
    pp(make_request("/bookings", "POST", {
        "room_id": 3,
        "user": "dave@corp.com",
        "start": "2026-08-10T11:00:00",
        "end": "2026-08-10T12:00:00"
    }))

    # 6. Cancel the whole series in one call (the office-manager endpoint)
    if series_id:
        say("6. Cancel the whole series in one call (the office-manager endpoint)")
        print("   All future instances are cancelled; past instances would be left intact")
        pp(make_request(f"/series/{series_id}", "DELETE"))

    say("Done.")

if __name__ == "__main__":
    main()
