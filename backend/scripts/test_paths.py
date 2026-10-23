"""路径冒烟：合同驳回、撤回作废、开票审批+发票登记+到账全链路。"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = "http://127.0.0.1:8000/api/v1"
TOK: dict[str, str] = {}
FAILED: list[str] = []


def req(method, path, token=None, body=None, form=None, file=None, params=None):
    if params:
        path = f"{path}?{urllib.parse.urlencode(params)}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if file is not None:
        boundary = "----t" + uuid.uuid4().hex
        out = bytearray()
        for k, v in (form or {}).items():
            out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
        n, fn, ct, payload = file
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{n}\"; filename=\"{fn}\"\r\n"
                f"Content-Type: {ct}\r\n\r\n").encode()
        out += payload + f"\r\n--{boundary}--\r\n".encode()
        data = bytes(out)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            p = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        p = json.loads(e.read() or b"{}")
    if p.get("code") != 0:
        raise RuntimeError(f"{method} {path} -> {p.get('code')} {p.get('message')}")
    return p.get("data")


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (" | " + detail if detail else ""))
    if not ok:
        FAILED.append(name + " " + detail)


def todo(token, biz_type, biz_id):
    d = req("GET", "/approval/tasks", token, params={"tab": "todo", "size": 200})
    for it in d["items"]:
        if it["bizType"] == biz_type and it["bizId"] == biz_id:
            return it["id"]
    return None


def main():
    for u in ("admin", "manager1", "leader1"):
        pwd = "Admin@123456" if u == "admin" else "Test@123456"
        TOK[u] = req("POST", "/auth/login", body={"username": u, "password": pwd})["access_token"]
    a, m, l = TOK["admin"], TOK["manager1"], TOK["leader1"]

    cust = req("POST", "/crm/customers", a, body={
        "name": "路径冒烟-合肥样例汽车科技有限公司", "customerType": "enterprise",
        "taxNo": f"91340100SMOKE{uuid.uuid4().hex[:6].upper()}", "status": "enabled",
        "country": "中国", "province": "安徽", "city": "合肥",
        "address": "合肥经济技术开发区始信路88号", "contactPerson": "王试", "contactPhone": "13800001234",
        "payOrg": "合肥样例汽车科技有限公司", "bankName": "中国工商银行合肥高新支行",
        "bankAccount": "1301021234567890123",
    })
    cid = cust["id"]

    def mk(name, amount):
        return req("POST", "/contract/contracts", a, body={
            "name": name, "customerId": cid, "contractType": "testing",
            "subjectType": "整车检测服务", "amount": amount,
            "startDate": "2026-06-01", "endDate": "2026-12-01", "payCycle": "once",
            "delivery": "report", "sealType": "合同专用章",
            "paymentOrg": cust["payOrg"], "contactPerson": "王试", "contactPhone": "13800001234",
        })

    # 1. 驳回
    c1 = mk("冒烟-合同A-驳回路径", 120000)
    req("POST", f"/contract/contracts/{c1['id']}/submit", a, body={"comment": ""})
    t = todo(m, "contract", c1["id"])
    check("reject.todo", t is not None, str(t))
    if t:
        req("POST", f"/approval/tasks/{t}/reject", m, body={"comment": "付款节点需调整"})
    st = req("GET", f"/contract/contracts/{c1['id']}", a)["status"]
    check("contract.rejected", st == "rejected", f"status={st}")

    # 2. 撤回 + 作废
    c2 = mk("冒烟-合同B-撤回作废", 80000)
    req("POST", f"/contract/contracts/{c2['id']}/submit", a, body={"comment": ""})
    detail = req("GET", f"/contract/contracts/{c2['id']}", a)
    inst = detail.get("flowInstanceId")
    check("void.instance_id", bool(inst), str(inst))
    if inst:
        req("POST", f"/approval/instances/{inst}/withdraw", a)
    st = req("GET", f"/contract/contracts/{c2['id']}", a)["status"]
    check("contract.withdrawn->draft", st == "draft", f"status={st}")
    req("POST", f"/contract/contracts/{c2['id']}/void", a)
    st = req("GET", f"/contract/contracts/{c2['id']}", a)["status"]
    check("contract.voided", st == "voided", f"status={st}")

    # 3. 通过
    c3 = mk("冒烟-合同C-通过", 300000)
    req("POST", f"/contract/contracts/{c3['id']}/submit", a, body={"comment": ""})
    t = todo(m, "contract", c3["id"])
    if t:
        req("POST", f"/approval/tasks/{t}/approve", m, body={"comment": "同意"})
    t = todo(l, "contract", c3["id"])
    if t:
        req("POST", f"/approval/tasks/{t}/approve", l, body={"comment": "同意"})
    st = req("GET", f"/contract/contracts/{c3['id']}", a)["status"]
    check("contract.approved", st == "approved", f"status={st}")

    # 4. 任务全链路 + 结算 + 开票 + 到账
    task = req("POST", "/task/tasks", a, body={
        "taskName": "冒烟-整车气动风洞试验", "taskType": "windtunnel", "contractId": c3["id"],
        "content": "依据 GB/T 12583-2010 开展风阻试验。", "receiver": "张伟",
        "receiverUnit": cust["name"], "bizBlock": "windtunnel_dept", "deptId": 3,
        "deptName": "风洞试验部", "ownerName": "张伟", "planFinishDate": "2026-09-20",
        "items": [{"itemCode": "ITEM01", "name": "整车风阻试验", "std": "GB/T 12583-2010",
                   "dept": "气动声学风洞", "inspector": "刘洋", "qty": 1, "settleType": "按次",
                   "needReport": 1}],
        "samples": [{"name": "DS-A1 样车#1", "model": "ST-5200", "vin": "LJ1ABCDEFG1234567",
                     "vehicleType": "纯电动乘用车", "sampleDate": "2026-06-10", "inStock": "in"}],
    })
    tid = task["id"]
    req("POST", f"/task/tasks/{tid}/submit", a)
    item = req("GET", f"/task/tasks/{tid}", a)["items"][0]
    check("task.report_no", bool(item.get("reportNo")), str(item.get("reportNo")))

    def docx():
        import io
        import zipfile
        buf = io.BytesIO()
        doc = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
               'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>冒烟报告</w:t></w:r></w:p></w:body></w:document>')
        ct = ('<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument'
              '.wordprocessingml.document.main+xml"/></Types>')
        rels = ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                'relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
                '2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("[Content_Types].xml", ct)
            z.writestr("_rels/.rels", rels)
            z.writestr("word/document.xml", doc)
        return buf.getvalue()

    rep = req("POST", "/report/reports", a, form={"item_id": str(item["id"])},
              file=("file", "冒烟报告.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx()))
    check("report.upload", rep.get("status") == "uploaded", str(rep))
    req("POST", f"/report/reports/{rep['id']}/submit", a)
    t = todo(m, "report", rep["id"])
    check("report.todo", t is not None, str(t))
    if t:
        req("POST", f"/approval/tasks/{t}/approve", m, body={"comment": "同意签批"})
    req("POST", f"/report/reports/{rep['id']}/seal", a)
    r = req("GET", f"/report/reports/{rep['id']}", a)
    check("report.sealed", r.get("status") == "sealed", f"status={r.get('status')}")

    req("POST", f"/task/tasks/{tid}/finish", a)
    st = req("GET", f"/task/tasks/{tid}", a)["status"]
    check("task.finished", st == "finished", f"status={st}")

    s = req("POST", "/finance/settlements", a, body={"taskId": tid, "amount": 50000,
                                                     "invoiceableAmount": 50000, "remark": "冒烟结算"})
    sid = s["id"]
    check("settlement.create", s.get("settlementNo", "").startswith("HK"), str(s.get("settlementNo")))
    req("POST", f"/finance/settlements/{sid}/apply-invoice", a, body={"comment": "冒烟开票"})
    t = todo(m, "invoice", sid)
    check("invoice.todo", t is not None, str(t))
    if t:
        req("POST", f"/approval/tasks/{t}/approve", m, body={"comment": "同意开票"})
    d = req("GET", f"/finance/settlements/{sid}", a)
    invs = d.get("invoices") or []
    check("invoice.issued", len(invs) == 1, str(len(invs)))
    if invs:
        out = req("PUT", f"/finance/invoices/{invs[0]['id']}", a,
                  body={"invoiceNo": "25340111000012345678", "amount": 50000,
                        "invoiceDate": "2026-10-08"})
        check("invoice.register", True, str(out)[:80])
    pay = req("POST", "/finance/payments", a, body={
        "settlementId": sid, "payType": "bank", "payerName": cust["name"],
        "payerAccount": "1301021234567890123", "amount": 50000, "bank": "中国工商银行合肥高新支行",
        "paidAt": "2026-10-10", "remark": "电汇"})
    check("payment.create", bool(pay), str(pay)[:80])
    d = req("GET", f"/finance/settlements/{sid}", a)
    check("settlement.paid", d.get("status") == "paid", f"status={d.get('status')} paid={d.get('paidAmount')}")

    print("\n" + ("ALL PASS" if not FAILED else f"FAILED: {FAILED}"))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
