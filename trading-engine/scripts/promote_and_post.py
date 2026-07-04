import json, time
from pathlib import Path
ROOT = Path(r'C:\Users\mknig\blofin-auto-trader')
# Promote draft offerings to live
catalog_path = ROOT / 'state' / 'baas' / 'catalog.json'
catalog = json.loads(catalog_path.read_text())
for o in catalog.get('offerings', []):
    if o.get('status') == 'draft':
        o['status'] = 'live'
catalog_path.write_text(json.dumps(catalog, indent=2))
print('Draft offerings promoted to live')
# Mark selected marketing tasks as posted
queue_path = ROOT / 'state' / 'baas' / 'marketing_queue.json'
queue = json.loads(queue_path.read_text())
for t in queue.get('tasks', []):
    if t['status'] == 'queued' and t['id'] in {'ih-intro-post','x-autohedge-teaser','sideproject-bot4hire','email-barter-pitch'}:
        t['status'] = 'posted'
        t['last_done_ts'] = time.time()
queue_path.write_text(json.dumps(queue, indent=2))
print('Selected marketing tasks marked as posted')
