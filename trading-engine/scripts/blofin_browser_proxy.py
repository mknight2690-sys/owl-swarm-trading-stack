from http.server import HTTPServer, BaseHTTPRequestHandler
import json, time, base64, hmac, hashlib, uuid
from urllib.parse import urlencode

from curl_cffi import requests

BASE = "https://openapi.blofin.com"
BROKER = "5388cb1f51cec2e3"

session = requests.Session(impersonate="edge101")
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://blofin.com",
    "Referer": "https://blofin.com/",
    "Content-Type": "application/json",
})

# Load credentials from the compendium file
cred_path = "C:/Users/mknig/Downloads/MK Blo Openclaw API compendium.txt"
fields = {}
for line in open(cred_path, encoding="utf-8").read().splitlines():
    if ":" in line:
        k, v = line.split(":", 1)
        fields[k.strip().lower().replace(" ", "_")] = v.strip()

API_KEY = fields.get("api_key") or fields.get("apikey")
SECRET = fields.get("secret_key") or fields.get("secretkey")
PASS_PHRASE = fields.get("passphrase")

def sign(method, full_path, body=""):
    ts = str(int(time.time() * 1000))
    nonce = str(uuid.uuid4())
    pre = f"{full_path}{method.upper()}{ts}{nonce}{body}"
    sig = base64.b64encode(hmac.new(SECRET.encode(), pre.encode(), hashlib.sha256).hexdigest().encode()).decode()
    return ts, nonce, sig

def api(method, path, body=None, params=None):
    url = BASE + path
    if params:
        url = url + "?" + urlencode(params)
    body_str = json.dumps(body, separators=(",", ":")) if body else ""
    ts, nonce, sig = sign(method, path, body_str)
    h = dict(session.headers)
    h.update({
        "ACCESS-KEY": API_KEY,
        "ACCESS-SIGN": sig,
        "ACCESS-TIMESTAMP": ts,
        "ACCESS-NONCE": nonce,
        "ACCESS-PASSPHRASE": PASS_PHRASE,
    })
    try:
        r = session.request(method.upper(), url, headers=h, data=body_str if body else None, timeout=20)
        if r.status_code == 200:
            try:
                return r.status_code, r.json()
            except Exception:
                return r.status_code, {"raw": r.text[:200]}
        else:
            return r.status_code, {"raw": r.text[:200], "status": r.status_code}
    except Exception as e:
        return 0, {"error": str(e)}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        sc, data = api("GET", self.path)
        self.send_response(200 if sc == 200 else sc)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(length)) if length else None
        sc, data = api("POST", self.path, body=body)
        self.send_response(200 if sc == 200 else sc)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        pass

server = HTTPServer(("127.0.0.1", 9876), Handler)
print("PROXY_READY 127.0.0.1:9876", flush=True)
server.serve_forever()
