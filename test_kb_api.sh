#!/bin/bash
# KB API 测试脚本
BASE="http://localhost:8201"

# 1. 获取 token
echo "=== 登录 ==="
TOKEN=$(curl -s -X POST "$BASE/api/v2/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import json,sys; print(json.load(sys.stdin).get('token',''))")
echo "Token: ${TOKEN:0:20}..."

# 2. KB 状态
echo -e "\n=== KB 状态 ==="
curl -s "$BASE/api/v2/kb/status" -H "Authorization: Bearer $TOKEN"

# 3. 向量搜索
echo -e "\n\n=== 向量搜索: 营业执照 ==="
curl -s -G "$BASE/api/v2/kb/search" \
  --data-urlencode "q=营业执照" \
  --data-urlencode "mode=vector" \
  --data-urlencode "top_k=3" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "
import json,sys
d=json.load(sys.stdin)
if d.get('detail'): print(f'Error: {d[\"detail\"]}'); exit()
print(f'Results: {d[\"total\"]} mode={d[\"mode\"]}')
for r in d['results']:
    print(f'  [{r[\"doc_id\"]}] {r.get(\"title\",\"?\")} score={r[\"score\"]}')
"

# 4. 多跳搜索
echo -e "\n=== 多跳搜索: ISO认证 ==="
curl -s -G "$BASE/api/v2/kb/search/multihop" \
  --data-urlencode "q=ISO认证" \
  --data-urlencode "top_k=3" \
  --data-urlencode "explain=true" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "
import json,sys
d=json.load(sys.stdin)
if d.get('detail'): print(f'Error: {d[\"detail\"]}'); exit()
print(f'Results: {d[\"total\"]}')
for r in d['results']:
    print(f'  [{r[\"doc_id\"]}] {r.get(\"title\",\"?\")} score={r[\"score\"]}')
if d.get('trace'):
    t=d['trace']
    print(f'Trace: {t[\"total_ms\"]}ms E={t[\"entities_found\"]} Ev={t[\"events_found\"]}')
"

# 5. 实体搜索
echo -e "\n=== 实体搜索 ==="
curl -s -G "$BASE/api/v2/kb/entities/search" \
  --data-urlencode "q=恒远" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "
import json,sys
d=json.load(sys.stdin)
if d.get('detail'): print(f'Error: {d[\"detail\"]}'); exit()
for e in d.get('entities',[]):
    print(f'  [{e[\"id\"]}] {e[\"name\"]} ({e[\"entity_type\"]})')
"

echo -e "\n✅ API 测试完成"
