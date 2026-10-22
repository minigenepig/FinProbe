# Mock ERP

模拟启衡精密制造有限公司 P2P ERP。这是普通 HTTP 服务，不是 MCP。

```powershell
python mock-erp/server.py
```

```powershell
curl.exe http://127.0.0.1:8081/health

curl.exe -H "X-Api-Key: qh_live_5fc45e4c22871d81ef7d47ea7b69aa2f" "http://127.0.0.1:8081/v1/vendors/VEN-0044"

curl.exe -H "X-Api-Key: qh_live_5fc45e4c22871d81ef7d47ea7b69aa2f" "http://127.0.0.1:8081/v1/invoices?supplierId=VEN-0121&page=1&pageSize=5"

curl.exe -H "X-Api-Key: qh_live_5fc45e4c22871d81ef7d47ea7b69aa2f" "http://127.0.0.1:8081/v1/payments?invoiceId=INV-004207"

curl.exe -H "X-Api-Key: qh_live_5fc45e4c22871d81ef7d47ea7b69aa2f" "http://127.0.0.1:8081/v1/approvals?businessId=VEN-0044"

curl.exe -H "X-Api-Key: qh_live_5fc45e4c22871d81ef7d47ea7b69aa2f" "http://127.0.0.1:8081/v1/policies?keyword=500000"
```

列表默认 pageSize=20，最大 100。Agent 不应直接 curl；由 mcp-server 代为调用。
