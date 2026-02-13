import os
import time
import json
import hashlib
import threading
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, render_template_string
from kubernetes import client, config
from kubernetes.client.rest import ApiException

DATA_DIR = os.getenv("DATA_DIR", "/data")
EVENTS_FILE = os.path.join(DATA_DIR, "events.json")
STATE_FILE  = os.path.join(DATA_DIR, "state.json")

INTERVAL_SECONDS = int(os.getenv("INTERVAL_SECONDS", "30"))
COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "600"))
NAMESPACES = [x.strip() for x in os.getenv("NAMESPACES", "").split(",") if x.strip()]

ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "")
ALERT_EMAIL_TO   = os.getenv("ALERT_EMAIL_TO", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

app = Flask(__name__)

def now_utc_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)

def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
    os.replace(tmp, path)

def fp(ns, pod, container, reason):
    raw = f"{ns}|{pod}|{container}|{reason}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def send_gmail(subject: str, body: str) -> bool:
    if not (ALERT_EMAIL_FROM and ALERT_EMAIL_TO and GMAIL_APP_PASSWORD):
        print(f"[{now_utc_iso()}] Email env vars missing; printing alert:\n{subject}\n{body}\n")
        return False

    recipients = [x.strip() for x in ALERT_EMAIL_TO.split(",") if x.strip()]
    msg = EmailMessage()
    msg["From"] = ALERT_EMAIL_FROM
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(ALERT_EMAIL_FROM, GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
        return True
    except Exception as e:
        print(f"[{now_utc_iso()}] Email send failed: {e}")
        return False

def get_ngrok_public_url() -> str:
    """
    Option A:
    ngrok sidecar exposes a local API at 127.0.0.1:4040 (inside the same pod).
    We read the current public URL and show it in the dashboard.
    """
    try:
        r = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=1.5)
        data = r.json()
        tunnels = data.get("tunnels", [])
        # Prefer https URL if available
        for t in tunnels:
            url = (t.get("public_url") or "").strip()
            if url.startswith("https://"):
                return url
        if tunnels:
            return (tunnels[0].get("public_url") or "").strip()
        return ""
    except Exception:
        return ""

def list_crashloops(v1: client.CoreV1Api):
    items = []

    def scan_pods(pod_list):
        for pod in pod_list.items:
            ns = pod.metadata.namespace
            name = pod.metadata.name
            statuses = (pod.status.container_statuses or []) + (pod.status.init_container_statuses or [])
            for st in statuses:
                waiting = st.state.waiting if st.state else None
                if waiting and (waiting.reason == "CrashLoopBackOff"):
                    items.append({
                        "time": now_utc_iso(),
                        "namespace": ns,
                        "pod": name,
                        "container": st.name,
                        "restarts": st.restart_count or 0,
                        "message": (waiting.message or "")[:500],
                        "reason": "CrashLoopBackOff"
                    })

    if NAMESPACES:
        for ns in NAMESPACES:
            scan_pods(v1.list_namespaced_pod(ns))
    else:
        scan_pods(v1.list_pod_for_all_namespaces())

    return items

def monitor_loop():
    config.load_incluster_config()
    v1 = client.CoreV1Api()

    ensure_data_dir()
    state = load_json(STATE_FILE, {})   # fp -> last_sent_epoch
    events = load_json(EVENTS_FILE, []) # list of events

    print(f"[{now_utc_iso()}] Monitor started. interval={INTERVAL_SECONDS}s cooldown={COOLDOWN_SECONDS}s namespaces={NAMESPACES or 'ALL'}")

    while True:
        try:
            crashloops = list_crashloops(v1)
            now_epoch = int(time.time())

            for e in crashloops:
                key = fp(e["namespace"], e["pod"], e["container"], e["reason"])
                last_sent = int(state.get(key, 0))

                if now_epoch - last_sent >= COOLDOWN_SECONDS:
                    subject = f"[K8s ALERT] CrashLoopBackOff: {e['namespace']}/{e['pod']} ({e['container']})"
                    body = (
                        f"Time: {e['time']}\n"
                        f"Namespace: {e['namespace']}\n"
                        f"Pod: {e['pod']}\n"
                        f"Container: {e['container']}\n"
                        f"Restarts: {e['restarts']}\n"
                        f"Message: {e['message'] or '—'}\n"
                    )
                    sent = send_gmail(subject, body)
                    if sent:
                        state[key] = now_epoch
                        save_json(STATE_FILE, state)

                    events.append({**e, "email_sent": bool(sent)})
                    events = events[-200:]
                    save_json(EVENTS_FILE, events)

            time.sleep(INTERVAL_SECONDS)

        except ApiException as ae:
            print(f"[{now_utc_iso()}] K8s API error: {ae.status} {ae.reason}")
            time.sleep(INTERVAL_SECONDS)
        except Exception as e:
            print(f"[{now_utc_iso()}] Unexpected error: {e}")
            time.sleep(INTERVAL_SECONDS)

TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>K8s CrashLoopBackOff Dashboard</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; }
    .card { padding: 16px; border: 1px solid #ddd; border-radius: 12px; margin-bottom: 16px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border-bottom: 1px solid #eee; padding: 10px; text-align: left; }
    th { background: #fafafa; }
    .pill { display:inline-block; padding: 4px 10px; border-radius: 999px; background:#ffecec; }
    code { background:#f6f6f6; padding:2px 6px; border-radius:6px; }
  </style>
</head>
<body>
  <h2>CrashLoopBackOff Dashboard</h2>

  <div class="card">
    <b>Public URL (ngrok):</b>
    {% if public_url %}
      <a href="{{ public_url }}" target="_blank">{{ public_url }}</a>
    {% else %}
      <span>Starting… (ngrok not ready yet)</span>
    {% endif %}
    <br/><br/>
    <b>Last refresh:</b> {{ refreshed }} <br/>
    <b>Namespaces:</b> {{ namespaces }}
  </div>

  <div class="card">
    <h3>Latest Alerts (last 200)</h3>
    <table>
      <tr><th>Time (UTC)</th><th>Namespace</th><th>Pod</th><th>Container</th><th>Restarts</th><th>Email</th></tr>
      {% for e in events %}
      <tr>
        <td>{{ e.time }}</td>
        <td><span class="pill">{{ e.namespace }}</span></td>
        <td>{{ e.pod }}</td>
        <td>{{ e.container }}</td>
        <td>{{ e.restarts }}</td>
        <td>{{ "✅" if e.email_sent else "❌" }}</td>
      </tr>
      {% endfor %}
    </table>
  </div>
</body>
</html>
"""

@app.get("/api/events")
def api_events():
    ensure_data_dir()
    events = load_json(EVENTS_FILE, [])
    return jsonify(events)

@app.get("/")
def home():
    ensure_data_dir()
    events = load_json(EVENTS_FILE, [])
    public_url = get_ngrok_public_url()
    return render_template_string(
        TEMPLATE,
        events=reversed(events),
        refreshed=now_utc_iso(),
        namespaces=",".join(NAMESPACES) if NAMESPACES else "ALL",
        public_url=public_url
    )

if __name__ == "__main__":
    ensure_data_dir()
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=8080)
