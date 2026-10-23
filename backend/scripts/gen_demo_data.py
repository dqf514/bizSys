"""仿真演示数据生成器：客户 / 合同 / 任务 / 报告 / 结算 / 开票 / 到账。

设计原则
- 全部走真实 HTTP API：编号规则、状态机、审批链、权限、审计由业务代码完成，不产生“脏数据”
- 内容仿真：真实省市/地址/开户行/税号格式、行业化合同与试验文案、GB/ISO 标准号、整车代号与 VIN
- 时间仿真：生成完再按“业务故事线”回填 create_time / update_time / 审批时间 / 签章时间，
  让列表、审批时间线、报表按自然时间分布（而不是全部落在今天）

用法（backend 容器内执行，需要容器内网 + DB 连接）：
    docker cp backend/scripts/gen_demo_data.py bizsys-api:/tmp/
    docker exec -w /app -e PYTHONPATH=/app bizsys-api python /tmp/gen_demo_data.py
    # 第二步：把 00:00:00 / 深夜时间规整到工作时间（见 fix_times.py）
    docker cp backend/scripts/fix_times.py bizsys-api:/tmp/
    docker exec -w /app -e PYTHONPATH=/app bizsys-api python /tmp/fix_times.py
可选参数：
    --customers N --contracts N --tasks N --no-backdate
"""

from __future__ import annotations

import argparse
import io
import json
import random
import string
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import date, datetime, timedelta

BASE = "http://127.0.0.1:8000/api/v1"
TODAY = date.today()
NOW = datetime.now()
R = random.Random(20261011)


# ---------------------------------------------------------------- HTTP 客户端

class ApiError(RuntimeError):
    pass


BOUNDARY = ""


def _multipart(fields: dict, file: tuple[str, str, str, bytes]) -> bytes:
    global BOUNDARY
    BOUNDARY = "----bizgen" + uuid.uuid4().hex
    b = BOUNDARY
    out = bytearray()
    for k, v in fields.items():
        out += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    name, filename, ctype, data = file
    out += (
        f"--{b}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
        f"Content-Type: {ctype}\r\n\r\n"
    ).encode()
    out += data
    out += f"\r\n--{b}--\r\n".encode()
    return bytes(out)


class Client:
    def __init__(self) -> None:
        self.tokens: dict[str, str] = {}

    def login(self, user: str, pwd: str) -> str:
        data = self.req("POST", "/auth/login", json_body={"username": user, "password": pwd})
        self.tokens[user] = data["access_token"]
        return data["access_token"]

    def tok(self, user: str) -> str:
        return self.tokens[user]

    def req(
        self,
        method: str,
        path: str,
        token: str | None = None,
        json_body=None,
        params: dict | None = None,
        form: dict | None = None,
        file: tuple[str, str, str, bytes] | None = None,
        retry: int = 2,
    ) -> dict:
        if params:
            path = f"{path}?{urllib.parse.urlencode(params)}"
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        body = None
        if file is not None:
            body = _multipart(form or {}, file)
            headers["Content-Type"] = f"multipart/form-data; boundary={BOUNDARY}"
        elif json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        payload = None
        last: Exception | None = None
        for _ in range(retry + 1):
            req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8") or "{}"
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {"code": e.code, "message": raw[:200]}
                break
            except Exception as e:  # 传输层抖动：换连接重试
                last = e
                time.sleep(0.25)
        if payload is None:
            raise ApiError(f"{method} {path} 网络失败: {last}")
        if payload.get("code") != 0:
            raise ApiError(f"{method} {path} -> code={payload.get('code')} {payload.get('message')}")
        return payload.get("data")


C = Client()


# ------------------------------------------------------------------ 仿真语料

REGIONS = [
    # (省, 市, 税号区划6位, 开发区叫法, 主干道)
    ("安徽", "合肥", "3401", "经济技术开发区", "始信路"),
    ("安徽", "芜湖", "3402", "高新技术产业开发区", "港湾路"),
    ("江苏", "苏州", "3205", "工业园区", "星湖街"),
    ("江苏", "常州", "3204", "武进高新区", "龙翔路"),
    ("江苏", "南京", "3201", "江宁开发区", "将军大道"),
    ("浙江", "宁波", "3302", "高新技术产业开发区", "振新路"),
    ("浙江", "温州", "3303", "经济技术开发区", "滨海大道"),
    ("上海", "上海", "3101", "临港新片区", "环湖西二路"),
    ("广东", "深圳", "4403", "南山科技园", "科苑大道"),
    ("广东", "东莞", "4419", "松山湖高新区", "工业北路"),
    ("广东", "佛山", "4406", "南海高新区", "桂澜北路"),
    ("湖北", "武汉", "4201", "东湖高新区", "光谷大道"),
    ("四川", "成都", "5101", "高新区西区", "天宇路"),
    ("山东", "青岛", "3702", "崂山区", "松岭路"),
    ("山东", "潍坊", "3707", "高新区", "卧龙东街"),
    ("北京", "北京", "1101", "亦庄经济技术开发区", "荣京东街"),
    ("陕西", "西安", "6101", "高新区", "科技二路"),
    ("重庆", "重庆", "5001", "两江新区", "金渝大道"),
    ("湖南", "长沙", "4301", "岳麓高新区", "麓谷大道"),
    ("河南", "郑州", "4101", "高新区", "莲花街"),
    ("福建", "厦门", "3502", "火炬高新区", "科华路"),
    ("天津", "天津", "1201", "滨海新区", "新城西路"),
    ("辽宁", "大连", "2102", "经济技术开发区", "淮河西路"),
    ("河北", "石家庄", "1301", "高新区", "昆仑大街"),
    ("江西", "南昌", "3601", "高新区", "艾溪湖一路"),
    ("广西", "南宁", "4501", "高新区", "科园大道"),
    ("云南", "昆明", "5301", "经开区", "云大西路"),
]

ZIHAO = [
    "晟泰", "瑞驰", "嘉禾", "鼎新", "弘毅", "博远", "中裕", "天成", "华翔", "金石",
    "瀚海", "绿能", "启越", "宸泰", "朗坤", "德茂", "盛达", "安泰", "科睿", "鑫源",
    "泰和", "鹏翔", "立诚", "信裕", "优铭", "驰创", "协力", "宇驰", "睿创", "新能跃",
    "恒擎", "越海", "九章", "行知", "明远", "致远", "云策", "拓元", "知行", "辰光",
    "启元", "同和", "永泰", "瑞和", "天工", "长风", "凌波", "望岳", "青枫", "白鹭",
]

INDUSTRIES = [
    ("新能源汽车", "科技有限公司", "enterprise"),
    ("汽车零部件", "制造有限公司", "enterprise"),
    ("动力电池", "技术有限公司", "enterprise"),
    ("电驱动系统", "有限公司", "enterprise"),
    ("智能装备", "股份有限公司", "enterprise"),
    ("精密机械", "有限公司", "enterprise"),
    ("机电科技", "有限公司", "enterprise"),
    ("工业技术", "有限公司", "enterprise"),
    ("汽车工程", "研究院有限公司", "research"),
    ("新能源技术", "研究院有限公司", "research"),
    ("材料科学", "研究所有限公司", "research"),
    ("检测技术", "研究院有限公司", "research"),
    ("汽车工程", "研究院", "research"),
    ("电子信息", "产业研究院有限公司", "research"),
    ("氢燃料电池", "科技有限公司", "enterprise"),
    ("车身轻量化", "技术有限公司", "enterprise"),
    ("车联网", "科技有限公司", "enterprise"),
    ("模具", "股份有限公司", "enterprise"),
    ("高分子材料", "有限公司", "enterprise"),
    ("质量检验", "研究院", "government"),
    ("计量测试", "研究所", "government"),
    ("产品监督检验院", "", "government"),
    ("特种设备检验检测院", "", "government"),
    ("交通运输科学研究院", "", "government"),
]

GRADE = ["A", "A", "B", "B", "B", "C", "C", "D"]

SURNAME = "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
GIVEN = [
    "志远", "晓峰", "海涛", "敏", "丽华", "帆", "国强", "雅静", "文斌", "桂兰",
    "建华", "雪梅", "伟", "俊杰", "晓东", "鹏", "诗涵", "文静", "天成", "磊",
    "秀英", "志强", "丹", "洋", "静", "浩", "欣", "晨", "宇", "琳",
    "嘉懿", "明轩", "子涵", "雨桐", "浩然", "梓萱", "一鸣", "振宇", "若曦", "佳怡",
]

MOBILE_PREFIX = ["131", "133", "135", "136", "137", "138", "139", "150", "151", "152", "155", "156",
                 "158", "159", "176", "177", "178", "182", "183", "186", "187", "188", "189", "199"]
LANDLINE_AREA = ["0551", "0512", "0574", "027", "028", "0532", "010", "029", "023", "0731", "0371", "0592"]

BANKS = ["中国工商银行", "中国建设银行", "中国农业银行", "中国银行", "交通银行", "招商银行",
         "兴业银行", "浦发银行", "中信银行", "民生银行"]
BANK_BRANCH = ["高新支行", "开发区支行", "城东支行", "营业部", "工业园支行", "新区支行", "科技园支行", "城西支行"]

PROV_TOKENS = ["中国", "安徽", "江苏", "浙江", "广东", "湖北", "四川", "山东", "北京", "陕西",
               "重庆", "湖南", "河南", "福建", "天津", "辽宁", "河北", "江西", "广西", "云南", "上海"]

CONTRACT_TYPES = ["testing", "testing", "testing", "testing", "service", "service", "sales", "framework"]
SUBJECTS = {
    "testing": ["整车检测服务", "零部件检测校准", "动力电池型式试验", "环境可靠性试验",
                "电磁兼容检测", "材料理化分析"],
    "service": ["技术咨询服务", "试验方案设计", "工程量清单与概算编制", "对标分析与改进建议",
                "认证辅导服务"],
    "sales": ["试验设备销售", "测控系统集成", "传感器与采集模块", "风洞辅助装置"],
    "framework": ["年度检测服务", "年度技术支持服务", "年度校准服务", "零部件批量检测"],
}
SEAL_TYPES = ["合同专用章", "公章", "法人名章", "财务专用章"]
PAY_CYCLES = ["monthly", "monthly", "quarterly", "once", "once"]
DELIVERY_WAYS = ["report", "report", "report", "onsite", "electronic"]

CONTRACT_REMARKS = [
    "按检测批次结算，报告签发后 30 日内付清全款。",
    "含两次现场复检，差旅费用由乙方承担。",
    "框架内单次委托按实际发生金额结算，季度汇总开票。",
    "合同金额含 13% 税率，开具增值税专用发票。",
    "首付款 30%，报告交付验收合格后支付尾款。",
    "试验周期紧张，需在合同签订后 15 个工作日内进场。",
    "长期合作客户，年度累计金额达标后按 5% 结算优惠。",
    "样品由客户送至试验室，回运费用自理。",
    "",
    "",
]

CAR_MODELS = [
    "DS-A1 纯电轿车", "DS-B3 混动 SUV", "DS-C5 纯电 MPV", "DS-D7 增程 SUV", "DS-E2 猎装版",
    "XV-P1 皮卡", "XV-N3 纯电物流车", "HX-M5 燃料电池客车", "HX-L8 纯电轻卡", "AT-Q6 智能轿车",
    "内部代号 FH-01", "内部代号 FH-03", "内部代号 ZK-12", "工程样车 ES-07", "量产复装车 PR-02",
]
PARTS = [
    "前保险杠总成", "进气格栅", "电池包下壳体", "前风窗玻璃", "外后视镜", "底盘护板",
    "驱动电机总成", "前舱支架", "侧围外板", "座椅骨架", "空调箱体", "快充接口",
]
PROJECTS = [
    "合肥新能源汽车产业园一期", "某车型产线柔性化改造", "商用车试验台架升级",
    "整车能耗与续航提升", "动力电池包结构优化", "车身轻量化材料应用",
    "电驱系统 NVH 改进", "智能座舱线束布线优化", "整车热管理系统匹配",
]
LABS = ["整车试验室", "电池试验室", "环境试验室", "气动声学风洞", "模型车间", "计量校准室", "电磁兼容室"]
ITEM_DEPTS = {
    "windtunnel": ["气动声学风洞", "整车试验室", "环境试验室", "电磁兼容室"],
    "model": ["模型车间", "计量校准室"],
    "consulting": ["工程咨询室", "技术经济室", "对标研究组", "项目管理组"],
}
SETTLE_TYPES = ["按次", "按件", "按台", "包干价"]

STDS = {
    "windtunnel": ["GB/T 12583-2010", "SAE J2071", "SAE J1252", "GB/T 29530-2013",
                   "GB/T 10485-2007", "GMW 14124", "FORD BO 160-1"],
    "model": ["GB/T 1804-2000", "GB/T 1184-1996", "QC/T 625-2013", "企业标准 Q/ST 07-2024",
              "ISO 2768-mK", "GB/T 4385-2017"],
    "consulting": ["GB 38031-2020", "GB/T 31467.3-2015", "GB/T 18655-2018", "ISO 6469-1:2019",
                   "GB 7258-2017", "C-NCAP 2024 版", "GB/T 28046.3-2011", "ISO 16750-2:2012",
                   "GB/T 2423.17-2008", "GB/T 31467.1-2015", "ECE R94", "GB/T 22128-2019",
                   "QC/T 740-2017", "GB/T 19951-2005", "ISO 19453-6:2017", "GB/T 2423.1-2008"],
}

CONTENT_TPL = {
    "windtunnel": [
        "在气动声学风洞开展{model}整车气动试验，环境温度 20±2℃、气压 101.3±0.5 kPa，"
        "测功机模拟满载工况，风速覆盖 30/60/90/120 km/h 四个特征点，每工况重复三次取均值。"
        "依据 {std} 输出风阻系数、升力系数与表面压力分布，附测点布置图与原始数据。",
        "{model}风噪与风阻优化验证试验：开启背景噪声修正，麦克风阵列按 {std} 布置 64 通道，"
        "对比 A/B 两版后视镜与格栅方案，出具 A 柱与后视镜区域噪声频谱对比报告。",
        "针对{part}方案开展风洞支架试验与旋转五分量天平标定，验证支架干扰修正系数，"
        "按 {std} 记录收敛判据，提供三次重复性数据与不确定度评定。",
    ],
    "model": [
        "制作{part} 1:1 试验模型：代木骨架 + 玻璃钢表面处理，配合比色与三坐标检测，"
        "关键尺寸公差按 {std} 执行，交付时附检测报告与曲面偏差云图。",
        "油泥模型制作与精修，含两轮造型评审修改；表面贴膜处理至 A 级曲面要求，"
        "交付周期 15 个工作日，附全尺寸扫描点云。",
        "{part}玻璃钢模型翻制：母模验收 → 分片翻制 → 合模修配 → 表面抛光喷漆，"
        "按 {std} 控制装配间隙，附三坐标检测记录与合模照片。",
    ],
    "consulting": [
        "{proj}工程量清单复核与概算编制：结合现行定额与材料价格信息，依据 {std} 完成清单复核"
        "与计价校核，出具概算书与咨询意见，含一次专家评审会并配合答疑。",
        "{proj}对标分析：采集竞品 6 台样车测试数据，按 {std} 逐项对比并给出改进建议，"
        "输出对标数据库与改进措施清单（含优先级排序）。",
        "{proj}可行性研究与投资估算：依据 {std} 编制投资估算并校核经济指标，"
        "出具可研报告送审稿，含两次现场踏勘与一次专家评审会。",
    ],
}

# 工程咨询类的依据分两类：计价/管理依据 vs 产品对标依据，别出现“按 C-NCAP 校核概算”这种硬伤
CONSULT_COST_STDS = [
    "GB 50500-2013 建设工程工程量清单计价规范",
    "GB/T 51262-2017 建设工程造价鉴定规范",
    "GB/T 50326-2017 建设工程项目管理规范",
    "《建设项目经济评价方法与参数》（第三版）",
]
CONSULT_STD_POOLS = [
    CONSULT_COST_STDS,     # 模板 0：清单复核与概算
    STDS["consulting"],    # 模板 1：对标分析
    CONSULT_COST_STDS,     # 模板 2：可研与投资估算
]

VIN_WMI = ["LJ1", "LSV", "LGB", "LVH", "LBE", "LDC", "L6T", "LZZ", "LV2", "LZW"]
VEHICLE_TYPES = ["纯电动乘用车", "插电式混合动力乘用车", "燃料电池城市客车", "纯电动轻型商用车", "工程机械车辆"]

SETTLE_REMARKS = [
    "按合同第三条结算，报告交付并验收合格后付款。",
    "季度汇总结算，随附试验明细清单。",
    "含现场服务费与标准物质消耗，实报实销部分另行确认。",
    "框架合同下单次委托结算，按实际发生金额开票。",
    "验收合格后 30 日内结清，逾期按合同约定计息。",
    "",
]
INVOICE_COMMENTS = ["", "按合同约定开具专用发票", "客户要求本月内开票", "随结算单附明细清单"]
PAY_REMARKS = ["", "电汇", "承兑汇票到期托收", "客户分两期支付", "财务对账后统一付款", ""]
PAY_TYPE_BY_REMARK = {"电汇": "bank_transfer", "承兑汇票到期托收": "draft"}


def rname() -> str:
    return SURNAME[R.randrange(len(SURNAME))] + GIVEN[R.randrange(len(GIVEN))]


def rdate(start: date, end: date) -> date:
    if end < start:
        start = end
    return start + timedelta(days=R.randint(0, (end - start).days))


def dt(d: date, h1: int = 8, h2: int = 19) -> datetime:
    return datetime(d.year, d.month, d.day, R.randint(h1, h2), R.randint(0, 59), R.randint(0, 59))


def money(lo: int, hi: int) -> float:
    v = R.randint(lo // 100, hi // 100) * 100
    return float(v + R.choice([0, 0, 0, 50, 80, 60, 99]))


def rand_alnum(n: int, pool: str = string.ascii_uppercase + string.digits) -> str:
    return "".join(R.choice(pool) for _ in range(n))


def tax_no(region: str) -> str:
    return f"91{region}{rand_alnum(8)}{R.choice(string.ascii_uppercase + string.digits)}"


def bank_account(region: str) -> str:
    head = R.choice(["1301", "1302", "3100", "4402", "1021", "2101"])
    return head + region[:2] + rand_alnum(R.randint(9, 12), string.digits)


def phone() -> str:
    if R.random() < 0.75:
        return R.choice(MOBILE_PREFIX) + "".join(R.choice(string.digits) for _ in range(8))
    return f"{R.choice(LANDLINE_AREA)}-{R.choice(['6', '8', '5'])}" + "".join(
        R.choice(string.digits) for _ in range(7)
    )


def vin() -> str:
    pool = string.ascii_uppercase + string.digits
    return R.choice(VIN_WMI) + rand_alnum(5, pool) + "".join(
        R.choice(string.digits) for _ in range(5)
    ) + rand_alnum(4, pool)


def invoice_no(d: date) -> str:
    """20 位全电发票号码：年份 + 流水。"""
    return f"{d.year}{rand_alnum(16, string.digits)}"


def make_docx(title: str, lines: list[str]) -> bytes:
    """最小但合法的 docx（报告原件），避免上传占位假文件。"""

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    paras = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{esc(t)}</w:t></w:r></w:p>' for t in [title, *lines]
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paras}</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument'
        '.wordprocessingml.document.main+xml"/></Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships'
        '/officeDocument" Target="word/document.xml"/></Relationships>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
    return buf.getvalue()


# -------------------------------------------------------------------- 生成器

class Gen:
    def __init__(self, n_customers: int, n_contracts: int, n_tasks: int) -> None:
        self.n_customer = n_customers
        self.n_contract = n_contracts
        self.n_task = n_tasks
        self.story: dict[str, list[tuple[int, datetime, datetime]]] = {}
        self.staff: list[dict] = []
        self.customers: list[dict] = []
        self.contracts: list[dict] = []
        self.tasks: list[dict] = []
        self.errors: list[str] = []

    # ---------- 工具 ----------
    def note(self, table: str, id_: int, created: datetime, updated: datetime | None = None) -> None:
        self.story.setdefault(table, []).append((id_, created, updated or created))

    @staticmethod
    def log(msg: str) -> None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

    def guard(self, what: str, fn) -> None:
        try:
            fn()
        except ApiError as e:
            self.errors.append(f"{what}: {e}")
            self.log(f"  !! {what}: {e}")

    def _todo(self, token: str, biz_type: str, biz_id: int) -> int | None:
        data = C.req("GET", "/approval/tasks", token, params={"tab": "todo", "size": 200})
        for it in data["items"]:
            if it["bizType"] == biz_type and it["bizId"] == biz_id:
                return it["id"]
        return None

    # ---------- 1. 员工账号 ----------
    def ensure_staff(self) -> None:
        admin = C.tok("admin")
        roles = C.req("GET", "/admin/roles", admin, params={"page": 1, "size": 200})
        biz_role = next(r["id"] for r in roles["items"] if r["code"] == "biz_user")
        depts = C.req("GET", "/admin/depts", admin)
        dept_by_name = {d["name"]: d for d in depts}

        staff = [
            ("zhangwei", "张伟", "工程咨询部"),
            ("lina", "李娜", "工程咨询部"),
            ("wanglei", "王磊", "模型加工中心"),
            ("chenjing", "陈静", "模型加工中心"),
            ("liuyang", "刘洋", "风洞试验部"),
            ("zhaomin", "赵敏", "风洞试验部"),
            ("sunhao", "孙浩", "风洞试验部"),
            ("zhouxue", "周雪", "综合管理部"),
        ]
        users = C.req("GET", "/admin/users", admin, params={"page": 1, "size": 200})
        by_name = {u["username"]: u for u in users["items"]}
        for username, name, dept in staff:
            if username not in by_name:
                d = dept_by_name.get(dept) or depts[0]
                created = C.req(
                    "POST",
                    "/admin/users",
                    admin,
                    json_body={
                        "username": username,
                        "password": "Staff@2026",
                        "name": name,
                        "deptId": d["id"],
                        "deptName": d["name"],
                        "mobile": phone(),
                        "email": f"{username}@hmvic.cn",
                        "status": "enabled",
                        "roleIds": [biz_role],
                    },
                )
                by_name[username] = created if isinstance(created, dict) and "id" in created else {"id": None}
            u = by_name[username]
            self.staff.append({"id": u.get("id"), "username": username, "name": name, "dept": dept})
        # 兜底：刷新一遍拿到 id
        if any(s["id"] is None for s in self.staff):
            users = C.req("GET", "/admin/users", admin, params={"page": 1, "size": 200})
            by_name = {u["username"]: u for u in users["items"]}
            for s in self.staff:
                s["id"] = by_name.get(s["username"], {}).get("id")
        self.log(f"员工账号 {len(self.staff)} 个（业务角色，密码 Staff@2026）")

    # ---------- 2. 客户 ----------
    def gen_customers(self) -> None:
        admin = C.tok("admin")
        used: set[str] = set()
        for i in range(self.n_customer):
            prov, city, region, devzone, road = REGIONS[i] if i < len(REGIONS) else R.choice(REGIONS)
            ctype = R.choice(["enterprise"] * 6 + ["research"] * 3 + ["government"] * 2 + ["other"])
            while True:
                if ctype == "government":
                    core = R.choice(["质量检验", "计量测试", "产品监督检验", "特种设备检验检测",
                                     "交通运输科学"])
                    suffix = R.choice(["研究院", "检验院", "研究所", "中心"])
                    name = (f"{city}{core}{suffix}" if R.random() < 0.5 else f"{prov}{core}{suffix}")
                else:
                    ind, suffix, _ = R.choice([x for x in INDUSTRIES if x[2] != "government"])
                    zh = R.choice(ZIHAO)
                    r = R.random()
                    name = f"{city}{zh}{ind}{suffix}" if r < 0.35 else (
                        f"{prov}{zh}{ind}{suffix}" if r < 0.6 else f"{zh}{ind}{suffix}")
                if name not in used:
                    used.add(name)
                    break

            contact = rname()
            body = {
                "name": name,
                "code": f"KH-{i + 1:03d}",
                "customerType": ctype,
                "taxNo": tax_no(region),
                "grade": R.choice(GRADE),
                "status": "enabled" if R.random() > 0.06 else "disabled",
                "country": "中国",
                "province": prov,
                "city": city,
                "address": f"{city}{devzone}{road}{R.randint(2, 399)}号"
                + (f"{R.randint(1, 6)}幢{R.randint(101, 2601)}室" if R.random() < 0.4 else ""),
                "bankName": f"{R.choice(BANKS)}{city}{R.choice(BANK_BRANCH)}",
                "bankAccount": bank_account(region),
                "payOrg": name if R.random() < 0.8 else f"{name}（分公司）",
                "contactPerson": contact,
                "contactPhone": phone(),
                "remark": R.choice([
                    "", "",
                    f"对接人{contact}，常规工作日 9:00-17:30 沟通。",
                    "长期合作客户，年度框架协议续签中。",
                    "开票需提前提供开票信息确认单。",
                    "样品收发需提前一天预约。",
                    "已通过供应商准入审核，账期按合同执行。",
                ]),
            }
            c = C.req("POST", "/crm/customers", admin, json_body=body)
            created = dt(rdate(TODAY - timedelta(days=720), TODAY - timedelta(days=30)))
            self.note("crm_customer", c["id"], created, created + timedelta(days=R.randint(0, 120)))
            self.customers.append({
                "id": c["id"], "no": c["customerNo"], "name": name, "grade": body["grade"],
                "contact": contact, "contactPhone": body["contactPhone"], "payOrg": body["payOrg"],
                "bankAccount": body["bankAccount"], "created": created, "ctype": ctype,
            })
        self.log(f"客户 {len(self.customers)} 个")

    # ---------- 3. 合同 ----------
    @staticmethod
    def _short_name(full: str) -> str:
        s = full
        for token in ("有限公司", "股份有限公司", "研究院", "研究所", "检验院", "中心", "院", "所"):
            s = s.replace(token, "")
        for p in PROV_TOKENS:
            s = s.replace(p, "")
        return (s[:6] or full[:8])

    def gen_contracts(self) -> None:
        admin, mgr, leader = C.tok("admin"), C.tok("manager1"), C.tok("leader1")
        users = C.req("GET", "/admin/users", admin, params={"page": 1, "size": 200})["items"]
        handlers = [u for u in users if u["username"] != "admin"]

        plan = ["approved"] * 84 + ["approving"] * 4 + ["draft"] * 5 + ["rejected"] * 4 + ["voided"] * 3
        R.shuffle(plan)
        if len(plan) < self.n_contract:
            plan += ["approved"] * (self.n_contract - len(plan))
        plan = plan[: self.n_contract]

        year = TODAY.year
        for want in plan:
            cust = R.choice(self.customers)
            ctype = R.choice(CONTRACT_TYPES)
            subject = R.choice(SUBJECTS[ctype])
            cn = self._short_name(cust["name"])

            if ctype == "framework":
                name = f"{cn}{year}年{subject}框架合同"
                amount = money(800_000, 6_800_000)
            elif ctype == "testing":
                name = f"{cn}{subject}合同（第{R.randint(1, 12)}批）"
                amount = money(60_000, 900_000)
            elif ctype == "service":
                name = f"{cn}{subject}合同"
                amount = money(120_000, 1_600_000)
            else:
                name = f"{cn}{subject}合同"
                amount = money(180_000, 4_800_000)

            sign = rdate(TODAY - timedelta(days=340), TODAY - timedelta(days=5))
            start = sign + timedelta(days=R.randint(0, 15))
            end = start + timedelta(days=30 * R.choice([3, 6, 6, 12, 12, 12]))
            handler = R.choice(handlers)
            c = C.req("POST", "/contract/contracts", admin, json_body={
                "name": name,
                "customerId": cust["id"],
                "contractType": ctype,
                "subjectType": subject,
                "amount": amount,
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "payCycle": R.choice(PAY_CYCLES),
                "delivery": R.choice(DELIVERY_WAYS),
                "sealType": R.choice(SEAL_TYPES),
                "handlerId": handler["id"],
                "handlerName": handler.get("name") or handler["username"],
                "frameworkNo": (f"KJ{sign.year}{R.randint(1, 60):04d}"
                                if ctype != "framework" and R.random() < 0.45 else ""),
                "paymentOrg": cust["payOrg"],
                "contactPerson": cust["contact"],
                "contactPhone": cust["contactPhone"],
                "remark": R.choice(CONTRACT_REMARKS),
            })
            cid = c["id"]
            submit_day = sign - timedelta(days=R.randint(0, 5))
            withdrawn = False

            if want == "approved":
                C.req("POST", f"/contract/contracts/{cid}/submit", admin, json_body={"comment": ""})
                self._approve(cid, "contract", mgr, leader, "同意，按合同条款执行。")
            elif want == "approving":
                C.req("POST", f"/contract/contracts/{cid}/submit", admin, json_body={"comment": ""})
            elif want == "rejected":
                C.req("POST", f"/contract/contracts/{cid}/submit", admin, json_body={"comment": ""})
                t = self._todo(mgr, "contract", cid)
                if t:
                    C.req("POST", f"/approval/tasks/{t}/reject", mgr,
                          json_body={"comment": "付款节点与公司财务制度不符，请调整后重新提交。"})
            elif want == "voided":
                if R.random() < 0.5:
                    C.req("POST", f"/contract/contracts/{cid}/submit", admin, json_body={"comment": ""})
                    detail = C.req("GET", f"/contract/contracts/{cid}", admin)
                    if detail.get("flowInstanceId"):
                        C.req("POST", f"/approval/instances/{detail['flowInstanceId']}/withdraw", admin)
                    C.req("POST", f"/contract/contracts/{cid}/void", admin)
                    withdrawn = True
                else:
                    C.req("POST", f"/contract/contracts/{cid}/void", admin)

            created = dt(submit_day - timedelta(days=R.randint(2, 15)))
            if want in ("approved", "rejected"):
                updated = dt(sign)
            elif withdrawn:
                updated = created + timedelta(hours=R.randint(2, 6))
            else:
                updated = created
            self.note("ctr_contract", cid, created, updated)
            self.contracts.append({
                "id": cid, "no": c["contractNo"], "name": name, "amount": amount, "status": want,
                "customer": cust, "start": start, "end": end, "ctype": ctype, "sign": sign,
            })

        approved = [x for x in self.contracts if x["status"] == "approved"]
        self.log(f"合同 {len(self.contracts)} 份（已通过 {len(approved)}）")

    def _approve(self, biz_id: int, biz_type: str, mgr: str, leader: str, comment: str) -> None:
        t = self._todo(mgr, biz_type, biz_id)
        if t:
            C.req("POST", f"/approval/tasks/{t}/approve", mgr, json_body={"comment": comment})
        t = self._todo(leader, biz_type, biz_id)
        if t:
            C.req("POST", f"/approval/tasks/{t}/approve", leader, json_body={"comment": "同意，走后续流程。"})

    # ---------- 4. 任务 ----------
    def gen_tasks(self) -> None:
        admin, mgr = C.tok("admin"), C.tok("manager1")
        approved = [x for x in self.contracts if x["status"] == "approved"]
        if not approved:
            raise RuntimeError("没有已通过合同，无法建任务")

        depts = C.req("GET", "/admin/depts", admin)
        dept_id = {d["name"]: d["id"] for d in depts}
        block_of = {"consulting": ("consulting_dept", "工程咨询部"),
                    "model": ("model_center", "模型加工中心"),
                    "windtunnel": ("windtunnel_dept", "风洞试验部")}

        plan = (["finished"] * 90 + ["in_progress"] * 85 + ["draft"] * 15 + ["stopped"] * 10)
        R.shuffle(plan)
        if len(plan) < self.n_task:
            plan += ["in_progress"] * (self.n_task - len(plan))
        plan = plan[: self.n_task]

        early = [c for c in approved if c["start"] <= TODAY - timedelta(days=60)]
        mid = [c for c in approved if c["start"] <= TODAY - timedelta(days=15)]

        for want in plan:
            if want in ("finished", "stopped"):
                pool = early or mid or approved
            elif want == "in_progress":
                pool = mid or approved
            else:
                pool = approved
            contract = R.choice(pool)
            ttype = R.choice(list(block_of))
            block, dept_name = block_of[ttype]
            owner = R.choice(self.staff)

            if ttype == "windtunnel":
                subject = R.choice(CAR_MODELS)
            elif ttype == "model":
                subject = R.choice(PARTS)
            else:
                subject = R.choice(PROJECTS)

            if want in ("finished", "stopped"):
                base_day = rdate(TODAY - timedelta(days=320), TODAY - timedelta(days=60))
            elif want == "in_progress":
                base_day = rdate(TODAY - timedelta(days=45), TODAY - timedelta(days=8))
            else:
                base_day = rdate(TODAY - timedelta(days=8), TODAY - timedelta(days=1))
            created_day = max(base_day, contract["start"] + timedelta(days=R.randint(0, 7)))
            if created_day > TODAY - timedelta(days=1):
                created_day = TODAY - timedelta(days=1)

            plan_finish = created_day + timedelta(days=R.randint(7, 45))
            if want in ("finished", "stopped") and plan_finish > TODAY - timedelta(days=5):
                plan_finish = TODAY - timedelta(days=R.randint(5, 30))
                if plan_finish <= created_day + timedelta(days=3):
                    plan_finish = created_day + timedelta(days=4)

            # 任务内容/条目/样品都围绕同一条主线（subject），且文案模板、后缀、标准号一一对应
            kw = {"model": R.choice(CAR_MODELS), "part": R.choice(PARTS),
                  "proj": R.choice(PROJECTS)}
            if ttype == "windtunnel":
                idx = R.randrange(3)
                kw["model"], kw["std"] = subject, R.choice(STDS["windtunnel"])
                suffix = ("整车气动风洞试验", "风噪与风阻优化试验", "气动天平与支架干扰试验")[idx]
                content = CONTENT_TPL["windtunnel"][idx].format(**kw)
                stds = STDS["windtunnel"]
                item_name = f"{subject}风洞试验"
                item_depts = ITEM_DEPTS["windtunnel"]
                settle_opts = ["按次", "按台", "按次", "包干价"]
            elif ttype == "model":
                idx = R.randrange(3)
                kw["part"], kw["std"] = subject, R.choice(STDS["model"])
                suffix = ("试验模型加工", "油泥模型制作", "模型翻制与装配")[idx]
                content = CONTENT_TPL["model"][idx].format(**kw)
                stds = STDS["model"]
                item_name = f"{subject}加工与检测"
                item_depts = ITEM_DEPTS["model"]
                settle_opts = ["按件", "按件", "按台"]
            else:
                idx = R.randrange(3)
                kw["proj"], kw["std"] = subject, R.choice(CONSULT_STD_POOLS[idx])
                suffix = ("工程量清单与概算编制", "对标分析与改进建议", "可行性研究与投资估算")[idx]
                content = CONTENT_TPL["consulting"][idx].format(**kw)
                stds = CONSULT_COST_STDS + STDS["consulting"]
                item_name = f"{subject}咨询服务"
                item_depts = ITEM_DEPTS["consulting"]
                settle_opts = ["包干价", "包干价", "按次"]
            tname = f"{subject}{suffix}"

            items = []
            for k in range(R.choice([1, 1, 2, 2, 3, 4])):
                items.append({
                    "itemCode": f"ITEM{k + 1:02d}",
                    "name": item_name if k == 0 else f"{item_name}（第{k + 1}项）",
                    "std": R.choice(stds),
                    "dept": R.choice(item_depts),
                    "inspector": R.choice(self.staff)["name"],
                    "qty": R.randint(1, 6),
                    "settleType": R.choice(settle_opts),
                    "needReport": 1 if (ttype != "model" and k == 0) else 0,
                })
            samples = []
            for k in range(R.choice([1, 1, 1, 2, 3])):
                if ttype == "windtunnel":
                    sname, smodel = f"{subject} 样车#{k + 1}", R.choice(["ST-5200", "HP-330", "M2-A样", "工程样车"])
                elif ttype == "model":
                    sname, smodel = f"{subject} 样件-{k + 1:02d}", R.choice(["A样件", "OTS件", "PP件", "B样件"])
                else:
                    sname, smodel = f"对标样车-{k + 1:02d}（{R.choice(CAR_MODELS)}）", R.choice(CAR_MODELS)
                samples.append({
                    "name": sname,
                    "model": smodel,
                    "vin": vin() if ttype != "model" or R.random() < 0.5 else "",
                    "vehicleType": R.choice(VEHICLE_TYPES),
                    "sampleDate": (created_day - timedelta(days=R.randint(0, 6))).isoformat(),
                    "inStock": "out" if want in ("finished", "stopped") else "in",
                })

            try:
                tid = self._make_task(admin, want, contract, ttype, block, dept_name, dept_id,
                                       owner, tname, content, items, samples, plan_finish,
                                       created_day, mgr)
            except ApiError as e:
                self.errors.append(f"task({tname}): {e}")
                self.log(f"  !! 任务失败 {tname}: {e}")
                continue
            if tid is None:
                continue

        self.log(f"任务 {len(self.tasks)} 条")

    def _make_task(self, admin, want, contract, ttype, block, dept_name, dept_id, owner, tname,
                   content, items, samples, plan_finish, created_day, mgr) -> int | None:
        t = C.req("POST", "/task/tasks", admin, json_body={
            "taskName": tname,
            "taskType": ttype,
            "contractId": contract["id"],
            "content": content,
            "receiver": R.choice(self.staff)["name"],
            "receiverUnit": contract["customer"]["name"],
            "bizBlock": block,
            "deptId": dept_id.get(dept_name),
            "deptName": dept_name,
            "ownerId": owner["id"],
            "ownerName": owner["name"],
            "partySystem": R.choice(["", "", "", "CNAS 实验室管理系统", "省特种设备监管平台", "企微审批"]),
            "planFinishDate": plan_finish.isoformat(),
            "items": items,
            "samples": samples,
        })
        tid = t["id"]
        detail = C.req("GET", f"/task/tasks/{tid}", admin)
        need_report_ids = [it["id"] for it in detail.get("items", []) if it.get("needReport")]

        step = created_day
        if want in ("in_progress", "finished", "stopped"):
            C.req("POST", f"/task/tasks/{tid}/submit", admin)
            step += timedelta(days=R.randint(0, 2))

        if want == "finished":
            ok = True
            for iid in need_report_ids:
                if not self._make_report(admin, mgr, iid, "sealed"):
                    ok = False
            if not ok:
                self.errors.append(f"task {t['taskNo']}: 报告未签章，无法 finish")
                want = "in_progress"
            else:
                try:
                    C.req("POST", f"/task/tasks/{tid}/finish", admin)
                    step += timedelta(days=R.randint(1, 4))
                except ApiError as e:
                    self.errors.append(f"task {t['taskNo']} finish: {e}")
                    want = "in_progress"
        elif want == "in_progress" and need_report_ids and R.random() < 0.7:
            for iid in need_report_ids:
                st = R.choice(["uploaded", "approving", "approved"])
                self._make_report(admin, mgr, iid, st)

        if want == "stopped":
            try:
                C.req("POST", f"/task/tasks/{tid}/stop", admin)
            except ApiError as e:
                self.errors.append(f"task {t['taskNo']} stop: {e}")

        created = dt(created_day)
        updated = dt(min(step, TODAY - timedelta(days=1)))
        if updated < created:
            updated = created
        self.note("task_task", tid, created, updated)
        self.tasks.append({
            "id": tid, "no": t["taskNo"], "name": tname, "contract": contract,
            "customer": contract["customer"], "want": want, "created_day": created_day,
            "plan_finish": plan_finish, "updated": updated, "ctype": ttype,
        })
        return tid

    def _make_report(self, admin: str, mgr: str, item_id: int, final: str) -> bool:
        """上传报告并推进到目标状态：uploaded / approving / approved / sealed"""
        try:
            rep = C.req(
                "POST", "/report/reports", admin,
                form={"item_id": str(item_id)},
                file=("file", f"检测报告-{rand_alnum(6)}.docx",
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                      make_docx("检测/试验报告", [
                          "受检单位：（详见附页）",
                          "样品名称：（详见原始记录）",
                          "试验依据：GB 38031-2020、GB/T 31467.3-2015",
                          "试验结论：所检项目符合标准要求。",
                      ])),
            )
        except ApiError as e:
            self.errors.append(f"report upload item={item_id}: {e}")
            self.log(f"  !! 报告上传失败 item={item_id}: {e}")
            return False
        rid = rep["id"]
        try:
            if final in ("approving", "approved", "sealed"):
                C.req("POST", f"/report/reports/{rid}/submit", admin)
            if final in ("approved", "sealed"):
                t = self._todo(mgr, "report", rid)
                if t:
                    C.req("POST", f"/approval/tasks/{t}/approve", mgr, json_body={"comment": "同意签批"})
            if final == "sealed":
                C.req("POST", f"/report/reports/{rid}/seal", admin)
        except ApiError as e:
            self.errors.append(f"report {rid} -> {final}: {e}")
            self.log(f"  !! 报告推进失败 {rid}: {e}")
            return False
        return True

    # ---------- 5. 财务 ----------
    def gen_finance(self) -> None:
        admin, mgr = C.tok("admin"), C.tok("manager1")
        finished = [t for t in self.tasks if t["want"] == "finished"]
        R.shuffle(finished)
        targets = finished[: max(1, int(len(finished) * 0.7))]

        stat = {"pending": 0, "invoicing": 0, "invoiced": 0, "paid": 0, "fail": 0}
        for t in targets:
            try:
                self._settle_one(admin, mgr, t, stat)
            except ApiError as e:
                stat["fail"] += 1
                self.errors.append(f"settlement {t['no']}: {e}")
                self.log(f"  !! 结算失败 {t['no']}: {e}")
        self.log(f"结算 {sum(v for k, v in stat.items() if k != 'fail')} 单："
                 f"待开票 {stat['pending']} / 开票审批中 {stat['invoicing']} / "
                 f"已开票未收齐 {stat['invoiced']} / 已到账 {stat['paid']}"
                 + (f" / 失败 {stat['fail']}" if stat['fail'] else ""))

    def _settle_one(self, admin: str, mgr: str, t: dict, stat: dict) -> None:
        contract_amount = float(t["contract"]["amount"] or 100000)
        amount = round(contract_amount * R.uniform(0.03, 0.22), 2)
        if amount < 3000:
            amount = float(R.randint(3, 40) * 1000)
        invoiceable = round(amount * R.choice([0.85, 0.9, 0.95]), 2) if R.random() < 0.2 else amount

        settle_day = min(t["plan_finish"] + timedelta(days=R.randint(3, 30)), TODAY - timedelta(days=3))
        if settle_day < t["created_day"] + timedelta(days=2):
            settle_day = t["created_day"] + timedelta(days=2)
        s = C.req("POST", "/finance/settlements", admin, json_body={
            "taskId": t["id"], "amount": amount, "invoiceableAmount": invoiceable,
            "remark": R.choice(SETTLE_REMARKS),
        })
        sid = s["id"]
        self.note("fin_settlement", sid, dt(settle_day), dt(settle_day))

        roll = R.random()
        if roll < 0.25:                      # 待开票
            stat["pending"] += 1
            return
        C.req("POST", f"/finance/settlements/{sid}/apply-invoice", admin,
              json_body={"comment": R.choice(INVOICE_COMMENTS)})
        if roll < 0.42:                      # 开票申请审批中
            stat["invoicing"] += 1
            return

        todo = self._todo(mgr, "invoice", sid)
        if todo:
            C.req("POST", f"/approval/tasks/{todo}/approve", mgr, json_body={"comment": "同意开票"})
        detail = C.req("GET", f"/finance/settlements/{sid}", admin)
        invs = detail.get("invoices") or []
        inv_day = min(settle_day + timedelta(days=R.randint(1, 8)), TODAY - timedelta(days=2))
        if invs:
            inv = invs[0]
            C.req("PUT", f"/finance/invoices/{inv['id']}", admin, json_body={
                "invoiceNo": invoice_no(inv_day), "amount": invoiceable,
                "invoiceDate": inv_day.isoformat(),
            })
            self.note("fin_invoice", inv["id"], dt(inv_day), dt(inv_day))

        full = R.random() < 0.62
        if full:
            n = 1 if R.random() < 0.55 else R.choice([2, 3])
            if n == 1:
                parts = [amount]
            else:
                cuts = sorted(R.uniform(0.25, 0.75) for _ in range(n - 1))
                vals, prev = [], 0.0
                for f in cuts:
                    vals.append(round(amount * (f - prev), 2))
                    prev = f
                vals.append(round(amount * (1 - prev), 2))
                parts = [v for v in vals if v > 0]
                parts[-1] = round(amount - sum(parts[:-1]), 2)
        else:
            paid = round(amount * R.uniform(0.3, 0.65), 2)
            if R.random() < 0.5:
                half = round(paid / 2, 2)
                parts = [half, round(paid - half, 2)]
            else:
                parts = [paid]

        pay_day = max(inv_day + timedelta(days=R.randint(5, 45)), inv_day + timedelta(days=3))
        last_pay = inv_day
        for part in parts:
            if pay_day > TODAY - timedelta(days=1):
                pay_day = TODAY - timedelta(days=1)
            if pay_day <= last_pay:
                break
            remark = R.choice(PAY_REMARKS)
            C.req("POST", "/finance/payments", admin, json_body={
                "settlementId": sid,
                "payType": PAY_TYPE_BY_REMARK.get(remark, R.choice(["bank_transfer", "bank_transfer", "draft", "pos"])),
                "payerName": t["customer"]["name"],
                "payerAccount": t["customer"]["bankAccount"],
                "amount": part,
                "bank": R.choice(BANKS) + R.choice(BANK_BRANCH),
                "paidAt": pay_day.isoformat(),
                "remark": remark,
            })
            last_pay = pay_day
            pay_day = pay_day + timedelta(days=R.randint(8, 35))
        if full:
            stat["paid"] += 1
            self.note("fin_settlement", sid, dt(settle_day), dt(last_pay))
        else:
            stat["invoiced"] += 1
            self.note("fin_settlement", sid, dt(settle_day), dt(last_pay))

    # ---------- 6. 时间回填 ----------
    def apply_backdate(self) -> None:
        from sqlalchemy import text

        from app.core.db import engine

        self.log("回填时间戳 …")
        with engine.begin() as conn:
            # 主体业务表
            for table, rows in self.story.items():
                for id_, ct, ut in rows:
                    conn.execute(
                        text(f"UPDATE {table} SET create_time=:ct, update_time=:ut WHERE id=:id"),
                        {"ct": ct, "ut": max(ut, ct), "id": id_},
                    )

            # 员工账号
            for s in self.staff:
                d = rdate(TODAY - timedelta(days=700), TODAY - timedelta(days=120))
                conn.execute(
                    text("UPDATE sys_user SET create_time=:ct, update_time=:ct WHERE username=:u"),
                    {"ct": dt(d), "u": s["username"]},
                )

            # 条目 / 样品 跟随任务
            conn.execute(text(
                "UPDATE task_item i JOIN task_task t ON t.id=i.task_id "
                "SET i.create_time=t.create_time, i.update_time=t.update_time"
            ))
            conn.execute(text(
                "UPDATE task_sample s JOIN task_task t ON t.id=s.task_id "
                "SET s.create_time=t.create_time, s.update_time=t.update_time"
            ))

            # 报告与报告文件跟随任务
            rows = conn.execute(text(
                "SELECT r.id, t.create_time FROM rpt_report r JOIN task_task t ON t.id=r.task_id "
                "WHERE r.deleted=0"
            )).all()
            for rid, t_created in rows:
                base = t_created + timedelta(days=R.randint(2, 20), hours=R.randint(1, 8))
                if base > NOW - timedelta(hours=6):
                    base = NOW - timedelta(days=1, hours=R.randint(2, 20))
                conn.execute(
                    text("UPDATE rpt_report SET create_time=:c, update_time=:u, "
                         "seal_time=IF(status='sealed', :s, NULL) WHERE id=:i"),
                    {"c": base, "u": base + timedelta(days=R.randint(0, 3)),
                     "s": base + timedelta(days=1), "i": rid},
                )
                conn.execute(
                    text("UPDATE rpt_file SET create_time=:c, update_time=:c "
                         "WHERE id IN (SELECT file_id FROM rpt_report WHERE id=:i "
                         "UNION SELECT pdf_file_id FROM rpt_report WHERE id=:i)"),
                    {"c": base, "i": rid},
                )

            # 到账记录以 paid_at 为准
            conn.execute(text(
                "UPDATE fin_payment SET create_time=COALESCE(paid_at, create_time), "
                "update_time=COALESCE(paid_at, update_time)"
            ))

            # 审批实例 / 记录 / 待办：锚点取业务对象的故事时间
            anchors: dict[tuple[str, int], tuple[datetime, datetime]] = {}
            for id_, ct, ut in self.story.get("ctr_contract", []):
                anchors[("contract", id_)] = (ct, ut)
            for id_, ct, _ in self.story.get("fin_settlement", []):
                anchors[("invoice", id_)] = (ct, ct + timedelta(days=1))
            for rid, ct in conn.execute(
                text("SELECT id, create_time FROM rpt_report WHERE deleted=0")
            ).all():
                anchors[("report", rid)] = (ct, ct + timedelta(days=R.randint(0, 2)))

            insts = conn.execute(text(
                "SELECT id, biz_type, biz_id, status FROM approval_instance WHERE deleted=0"
            )).all()
            for iid, biz_type, biz_id, status in insts:
                a = anchors.get((biz_type, biz_id))
                if not a:
                    continue
                begin = a[0] + timedelta(hours=R.randint(1, 6))
                if status == "running":
                    finish = None
                    end = begin + timedelta(minutes=45)
                else:
                    finish = a[1] + timedelta(hours=R.randint(1, 8))
                    if finish > NOW - timedelta(hours=2):
                        finish = NOW - timedelta(hours=2)
                    if finish <= begin + timedelta(hours=1):
                        begin = finish - timedelta(hours=2)
                        if begin < a[0]:
                            begin = a[0]
                            finish = max(finish, begin + timedelta(hours=1))
                    end = finish
                conn.execute(
                    text("UPDATE approval_instance SET create_time=:c, update_time=:u, "
                         "finished_at=:f WHERE id=:i"),
                    {"c": begin, "u": end, "f": finish, "i": iid},
                )
                recs = conn.execute(
                    text("SELECT id FROM approval_record WHERE instance_id=:i ORDER BY id"),
                    {"i": iid},
                ).scalars().all()
                span = max((end - begin).total_seconds(), 600)
                for n, rid in enumerate(recs):
                    at = begin + timedelta(seconds=span * (n + 1) / (len(recs) + 0.7))
                    conn.execute(
                        text("UPDATE approval_record SET at=:a, create_time=:a WHERE id=:r"),
                        {"a": at, "r": rid},
                    )
                tasks = conn.execute(
                    text("SELECT id, status FROM approval_task WHERE instance_id=:i"), {"i": iid}
                ).all()
                for n, (tid, st) in enumerate(tasks):
                    at = begin + timedelta(minutes=45 * (n + 1))
                    conn.execute(
                        text("UPDATE approval_task SET create_time=:c, "
                             "acted_at=CASE WHEN status='pending' THEN acted_at ELSE :a END "
                             "WHERE id=:i"),
                        {"c": at, "a": at, "i": tid},
                    )

            # 通知 / 审计 / 登录日志：打散
            conn.execute(text(
                "UPDATE sys_notify SET create_time=DATE_SUB(NOW(), INTERVAL FLOOR(1+RAND()*60) DAY) "
                "WHERE create_time > DATE_SUB(NOW(), INTERVAL 1 DAY)"
            ))
            conn.execute(text(
                "UPDATE sys_audit_log SET create_time=DATE_SUB(NOW(), INTERVAL FLOOR(RAND()*45) DAY) "
                "WHERE create_time > DATE_SUB(NOW(), INTERVAL 1 DAY)"
            ))
            conn.execute(text(
                "UPDATE sys_login_log SET create_time=DATE_SUB(NOW(), INTERVAL FLOOR(RAND()*45) DAY) "
                "WHERE create_time > DATE_SUB(NOW(), INTERVAL 1 DAY)"
            ))

            self._renumber(conn)
        self.log("时间回填完成")

    @staticmethod
    def _renumber(conn) -> None:
        """编号里的日期（HT202610110001）要与回填后的创建日期一致，否则一眼假。"""
        from sqlalchemy import text

        specs = [
            ("ctr_contract", "contract_no", "HT", "create_time", "deleted=0"),
            ("task_task", "task_no", "RW", "create_time", "deleted=0"),
            ("task_item", "report_no", "BG", "create_time", "deleted=0 AND report_no<>''"),
            ("fin_settlement", "settlement_no", "HK", "create_time", "deleted=0"),
            ("fin_payment", "payment_no", "DZ", "COALESCE(paid_at, create_time)", "deleted=0"),
        ]
        pairs: dict[str, str] = {}  # 旧编号 -> 新编号
        for table, col, prefix, date_expr, where in specs:
            rows = conn.execute(text(
                f"SELECT id, {date_expr}, {col} FROM {table} WHERE {where} ORDER BY {date_expr}, id"
            )).all()
            per_day: dict[str, int] = {}
            newmap: dict[int, str] = {}
            for id_, d, old in rows:
                if d is None:
                    continue
                key = d.strftime("%Y%m%d")
                per_day[key] = per_day.get(key, 0) + 1
                no = f"{prefix}{key}{per_day[key]:04d}"
                if old == no:
                    continue
                newmap[id_] = no
                if old:
                    pairs[old] = no
            for id_, no in newmap.items():  # 两阶段写入，避开唯一索引中间态冲突
                conn.execute(text(f"UPDATE {table} SET {col}=:n WHERE id=:i"),
                             {"n": f"__TMP__{no}", "i": id_})
            for id_, no in newmap.items():
                conn.execute(text(f"UPDATE {table} SET {col}=:n WHERE id=:i"), {"n": no, "i": id_})

        # 冗余字段与审批标题跟着走
        conn.execute(text(
            "UPDATE task_task t JOIN ctr_contract c ON c.id=t.contract_id "
            "SET t.contract_no=c.contract_no WHERE t.contract_id IS NOT NULL"
        ))
        conn.execute(text(
            "UPDATE fin_settlement s "
            "LEFT JOIN task_task t ON t.id=s.task_id "
            "LEFT JOIN ctr_contract c ON c.id=s.contract_id "
            "SET s.task_no=COALESCE(t.task_no, s.task_no), "
            "    s.contract_no=COALESCE(c.contract_no, s.contract_no)"
        ))
        conn.execute(text(
            "UPDATE rpt_report r JOIN task_item i ON i.id=r.task_item_id SET r.report_no=i.report_no"
        ))
        conn.execute(text(
            "UPDATE approval_instance a JOIN ctr_contract c "
            "ON a.biz_type='contract' AND a.biz_id=c.id "
            "SET a.title=CONCAT(c.contract_no, ' ', c.name)"
        ))
        conn.execute(text(
            "UPDATE approval_instance a JOIN fin_settlement s "
            "ON a.biz_type='invoice' AND a.biz_id=s.id "
            "SET a.title=CONCAT(s.settlement_no, ' 开票申请（', s.customer_name, '）')"
        ))
        conn.execute(text(
            "UPDATE approval_instance a JOIN rpt_report r "
            "ON a.biz_type='report' AND a.biz_id=r.id "
            "SET a.title=CONCAT(r.report_no, ' 报告签批')"
        ))

        # 审批快照 / 审计日志 / 通知正文里残留的旧编号一并替换（否则标题与快照对不上）
        if pairs:
            import re
            rx = re.compile("|".join(re.escape(o) for o in pairs))
            for tbl, cl in (("approval_instance", "form_snapshot"),
                            ("sys_audit_log", "detail"),
                            ("sys_notify", "content")):
                rows2 = conn.execute(text(
                    f"SELECT id, {cl} FROM {tbl} WHERE {cl} IS NOT NULL"
                )).all()
                for rid, val in rows2:
                    new = rx.sub(lambda m: pairs[m.group(0)], val)
                    if new != val:
                        conn.execute(text(f"UPDATE {tbl} SET {cl}=:v WHERE id=:i"),
                                     {"v": new, "i": rid})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--customers", type=int, default=50)
    ap.add_argument("--contracts", type=int, default=100)
    ap.add_argument("--tasks", type=int, default=200)
    ap.add_argument("--no-backdate", action="store_true")
    ap.add_argument("--check-only", action="store_true", help="只登录并检查是否已有数据")
    args = ap.parse_args()

    C.login("admin", "Admin@123456")
    C.login("manager1", "Test@123456")
    C.login("leader1", "Test@123456")
    C.req("GET", "/auth/me", C.tok("admin"))

    from sqlalchemy import text as _text

    from app.core.db import engine

    with engine.connect() as conn:
        existing = conn.execute(_text("SELECT COUNT(*) FROM crm_customer WHERE deleted=0")).scalar() or 0
    if args.check_only:
        print(f"existing customers: {existing}")
        return
    if existing >= args.customers:
        print(f"已有 {existing} 个客户（>= {args.customers}），跳过生成。")
        return

    g = Gen(args.customers, args.contracts, args.tasks)
    g.ensure_staff()
    g.gen_customers()
    g.gen_contracts()
    g.gen_tasks()
    g.gen_finance()
    if not args.no_backdate:
        g.apply_backdate()

    with engine.connect() as conn:
        for tbl in ("crm_customer", "ctr_contract", "task_task", "rpt_report",
                    "fin_settlement", "fin_invoice", "fin_payment", "sys_user"):
            n = conn.execute(_text(f"SELECT COUNT(*) FROM {tbl} WHERE deleted=0")).scalar()
            print(f"  {tbl}: {n}")
        print("--- 状态分布 ---")
        for r in conn.execute(_text(
            "SELECT 'contract', status, COUNT(*) FROM ctr_contract WHERE deleted=0 GROUP BY status"
        )).all():
            print(" ", *r)
        for r in conn.execute(_text(
            "SELECT 'task', status, COUNT(*) FROM task_task WHERE deleted=0 GROUP BY status"
        )).all():
            print(" ", *r)
        for r in conn.execute(_text(
            "SELECT 'settlement', status, COUNT(*) FROM fin_settlement WHERE deleted=0 GROUP BY status"
        )).all():
            print(" ", *r)
    if g.errors:
        print(f"\n非致命错误 {len(g.errors)} 条：")
        for e in g.errors[:20]:
            print("  -", e)
    print("DONE")


if __name__ == "__main__":
    main()
