import hashlib, json
data = '{"task_id":"test-ua-gwc-001","option":"OPT-1","accepted":true}'
print("sha256:" + hashlib.sha256(data.encode()).hexdigest())