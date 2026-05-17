import requests

# Start download (use low-res video for speed)
resp = requests.post('http://localhost:5000/download',
    json={'url': 'https://www.youtube.com/watch?v=jNQXAC9IVRw', 'resolution': '240p'})
print('Start:', resp.status_code, resp.json())

# Quick progress check
import time
for _ in range(5):
    time.sleep(2)
    prog = requests.get('http://localhost:5000/progress').json()
    print(f"  {prog.get('status')} | {prog.get('percent')} | {prog.get('speed')}")
    if prog.get('status') == 'finished':
        print('Done! File:', prog.get('filename'))
        break
