import requests
import time

for i in range(20):
    time.sleep(5)
    p = requests.get('http://localhost:5000/progress').json()
    print(f"[{i}] status={p.get('status')} percent={p.get('percent')} speed={p.get('speed')}")
    if p.get('status') in ('finished', 'error'):
        print("FINAL:", p)
        break
