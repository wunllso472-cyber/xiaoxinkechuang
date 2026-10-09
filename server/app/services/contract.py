"""合同智审：结构化解析、要素/条款抽取、模板差异对比、规则引擎合规审查。"""
import difflib
import json
import re

from ..llm import router as llm

# ---------------- 结构化 ----------------
HEAD_RE = re.compile(r"^\s*(第[一二三四五六七八九十百零\d]+[条章节]|[一二三四五六七八九十]+[、.．]|\d{1,2}[、.．](?!\d))\s*(.*)")


def split_clauses(text):
    """按“第X条 / 一、 / 1.”等标题切分条款，保持层级"""
    clauses, cur = [], {"title": "首部", "level": 0, "content": []}
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        m = HEAD_RE.match(s)
        if m and len(s) < 60:
            if cur["content"] or cur["title"] != "首部":
                clauses.append(cur)
            level = 1 if m.group(1).startswith("第") else 2
            cur = {"title": s, "level": level, "content": []}
        else:
            cur["content"].append(s)
    clauses.append(cur)
    for c in clauses:
        c["content"] = "\n".join(c["content"])
    return clauses


# ---------------- 金额 ----------------
CN_NUM = {"零": 0, "壹": 1, "贰": 2, "叁": 3, "肆": 4, "伍": 5, "陆": 6, "柒": 7, "捌": 8, "玖": 9,
          "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNIT = {"拾": 10, "十": 10, "佰": 100, "百": 100, "仟": 1000, "千": 1000}


def cn_money_to_num(s):
    s = s.replace("人民币", "").replace("整", "").replace("正", "")
    total, section, num = 0.0, 0, 0
    for ch in s:
        if ch in CN_NUM:
            num = CN_NUM[ch]
        elif ch in CN_UNIT:
            section += (num or 1) * CN_UNIT[ch]
            num = 0
        elif ch in ("万", "亿"):
            section += num
            total = (total + section) * (10000 if ch == "万" else 100000000)
            section, num = 0, 0
        elif ch in ("元", "圆"):
            section += num
            total += section
            section, num = 0, 0
        elif ch == "角":
            total += num * 0.1
            num = 0
        elif ch == "分":
            total += num * 0.01
            num = 0
    return round(total + section + num, 2)


def find_amounts(text):
    out = []
    for m in re.finditer(r"(?:¥|￥|人民币)?\s*([\d,]+(?:\.\d+)?)\s*(万元|元)", text):
        v = float(m.group(1).replace(",", "") or 0)
        out.append(v * 10000 if m.group(2) == "万元" else v)
    return out


# ---------------- 要素提取 ----------------
def _first(patterns, text):
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1).strip(" ：:，,。")
    return ""


def extract_elements(text):
    el = {
        "合同名称": _first([r"^\s*(.{2,40}合同)\s*$", r"(\S{2,30}(?:采购|服务|购销|技术)合同)"], text[:500]) or
                _first([r"(\S{2,30}合同)"], text[:300]),
        "合同编号": _first([r"合同编号[：:]\s*([A-Za-z0-9\-_/〔〕\[\]（）()]+)"], text),
        "甲方": _first([r"甲\s*方[（(]?[^）)\n]{0,6}[）)]?[：:]\s*([^\n，,]{2,40})", r"采购人[：:]\s*([^\n，,]{2,40})"], text),
        "乙方": _first([r"乙\s*方[（(]?[^）)\n]{0,6}[）)]?[：:]\s*([^\n，,]{2,40})", r"供应商[：:]\s*([^\n，,]{2,40})"], text),
        "合同金额(小写)": _first([r"(?:合同(?:总)?(?:金额|价款|总价)|总价款?)[^\n\d¥￥]{0,15}[¥￥]?\s*([\d,]+(?:\.\d+)?\s*(?:万元|元))",
                              r"[¥￥]\s*([\d,]+(?:\.\d+)?\s*元?)"], text),
        "合同金额(大写)": _first([r"(?:大写)[：:]?\s*(?:人民币)?([零壹贰叁肆伍陆柒捌玖拾佰仟万亿元圆角分整正]{2,})"], text),
        "签订日期": _first([r"签订(?:日期|时间)[：:]\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|\d{4}-\d{1,2}-\d{1,2})"], text),
        "履行期限": _first([r"((?:交货|交付|履行|服务|实施)(?:期限|期|时间)[^\n。]{0,60})"], text),
        "付款方式": _first([r"((?:付款|支付)(?:方式|条件|进度)?[：:][^\n]{0,80})", r"([^\n。]{0,20}(?:预付|首付|尾款)[^\n。]{0,60})"], text),
        "质保期": _first([r"((?:质保|保修|质量保证)期[^\n。]{0,40})"], text),
        "违约责任": _first([r"(违约[^\n。]{0,80})"], text),
        "争议解决/管辖地": _first([r"((?:争议|纠纷)[^\n。]{0,30}(?:法院|仲裁)[^\n。]{0,30})", r"((?:管辖)[^\n。]{0,40})"], text),
        "签字盖章": "已检测到" if re.search(r"(盖章|签章|签字|公章|合同专用章)", text) else "",
    }
    if el["合同金额(大写)"]:
        el["合同金额(大写)换算"] = cn_money_to_num(el["合同金额(大写)"])
    return el


def extract_entities(text):
    """命名实体：金额、时间、主体、地点"""
    return {
        "金额": list(dict.fromkeys(re.findall(r"[¥￥]?\s*[\d,]+(?:\.\d+)?\s*(?:万元|元)", text)))[:20],
        "时间": list(dict.fromkeys(re.findall(r"\d{4}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?|\d+\s*(?:个工作日|个自然日|日内|天内|个月)", text)))[:20],
        "主体": list(dict.fromkeys(re.findall(r"[一-龥（）()]{2,30}(?:公司|集团|中心|局|院|厅|委员会|学校|医院)", text)))[:20],
        "地点": list(dict.fromkeys(re.findall(r"[一-龥]{2,10}(?:省|市|区|县)(?:[一-龥]{2,10}(?:区|县|路|街))?", text)))[:20],
    }


def llm_extract(text):
    """可选：用大模型补全要素（模型未配置时返回空）"""
    prompt = ("从下面合同文本中提取要素，严格输出 JSON 对象，键为：合同名称、甲方、乙方、合同金额、履行期限、付款方式、"
              "违约责任、争议解决、质保期。没有的填空字符串。\n\n" + text[:6000])
    try:
        res = llm.chat([{"role": "system", "content": "你是合同审查专家，只输出JSON"},
                        {"role": "user", "content": prompt}], scene="contract", params={"temperature": 0.1})
        m = re.search(r"\{.*\}", res["content"], re.S)
        return json.loads(m.group(0)) if m else {}
    except Exception:  # noqa
        return {}


# ---------------- 模板差异 ----------------
def compare_template(text, clauses, template):
    """按模板条款定义做缺失/差异检测：关键词比对 + 文本相似度"""
    result = []
    for tc in template.clauses or []:
        kws = tc.get("keywords") or [tc["name"]]
        hit = [k for k in kws if k in text]
        best, best_ratio = None, 0.0
        for c in clauses:
            ratio = max(difflib.SequenceMatcher(None, tc["name"], c["title"]).ratio(),
                        1.0 if any(k in c["title"] for k in kws) else 0)
            if ratio > best_ratio:
                best, best_ratio = c, ratio
        if not hit:
            status, color = ("缺失", "red") if tc.get("required") else ("未包含(可选)", "gray")
        elif best_ratio < 0.5:
            status, color = "格式不符(未独立成条)", "orange"
        else:
            status, color = "一致", "green"
        item = {"clause": tc["name"], "required": tc.get("required", False), "status": status, "color": color,
                "matched_title": best["title"] if best and best_ratio >= 0.5 else "", "keywords_hit": hit}
        std = tc.get("standard_text")
        if std and best and best_ratio >= 0.5:
            sim = difflib.SequenceMatcher(None, std, best["content"][:len(std) * 2]).ratio()
            item["similarity"] = round(sim, 2)
            if sim < 0.6:
                item["status"], item["color"] = "内容冲突", "orange"
        result.append(item)
    return result


# ---------------- 规则引擎 ----------------
def run_rule(rule, text, elements):
    p = rule.params or {}
    t = rule.rule_type
    if t == "element_required":
        ok = bool(elements.get(p.get("element", ""), ""))
        return ok, "" if ok else "未识别到要素【%s】" % p.get("element")
    if t == "keyword_required":
        kws = p.get("keywords", [])
        hit = [k for k in kws if k in text]
        ok = bool(hit) if p.get("any", True) else len(hit) == len(kws)
        return ok, "" if ok else "缺少关键内容：%s" % "/".join(kws)
    if t == "keyword_forbidden":
        hit = [k for k in p.get("keywords", []) if k in text]
        return not hit, "出现不合规内容：%s" % "、".join(hit) if hit else ""
    if t == "regex_required":
        ok = re.search(p.get("pattern", ""), text) is not None
        return ok, "" if ok else p.get("message", "未匹配到要求的内容")
    if t == "regex_forbidden":
        m = re.search(p.get("pattern", ""), text)
        return m is None, ("出现不合规表述：%s" % m.group(0)[:50]) if m else ""
    if t == "amount_max":
        vals = []
        for m in re.finditer(p.get("pattern", r"单价[^\n\d]{0,10}([\d,]+(?:\.\d+)?)\s*元"), text):
            try:
                vals.append(float(m.group(1).replace(",", "")))
            except ValueError:
                pass
        over = [v for v in vals if v > float(p.get("max", 0))]
        return not over, "金额 %s 超过阈值 %s 元" % (over[:3], p.get("max")) if over else ""
    if t == "amount_consistent":
        small, big = elements.get("合同金额(小写)", ""), elements.get("合同金额(大写)换算")
        if not small or big is None:
            return True, ""
        sv = find_amounts(small)
        ok = not sv or abs(sv[0] - big) < 0.01
        return ok, "" if ok else "大小写金额不一致：小写 %s，大写换算 %s" % (small, big)
    if t == "llm":
        try:
            res = llm.chat([{"role": "system", "content": "你是合同合规审查专家。只回答“合规”或“不合规：原因”。"},
                            {"role": "user", "content": p.get("prompt", "") + "\n\n合同内容：\n" + text[:6000]}],
                           scene="contract", params={"temperature": 0.1})
            c = res["content"].strip()
            return not c.startswith("不合规"), c[:200]
        except Exception as e:  # noqa
            return True, "大模型审查跳过：%s" % e
    return True, ""


def review(text, elements, rules):
    items = []
    for r in rules:
        ok, msg = run_rule(r, text, elements)
        items.append({"rule_id": r.id, "code": r.code, "name": r.name, "category": r.category,
                      "level": r.level, "passed": ok, "message": msg})
    failed = [i for i in items if not i["passed"]]
    if any(i["level"] == "高" for i in failed):
        risk = "高"
    elif any(i["level"] == "中" for i in failed):
        risk = "中"
    elif failed:
        risk = "低"
    else:
        risk = "无"
    return items, risk


# ---------------- 默认审查规则（30+） ----------------
DEFAULT_RULES = [
    ("R001", "合同名称完整", "要素完整性", "element_required", {"element": "合同名称"}, "低"),
    ("R002", "甲方信息完整", "要素完整性", "element_required", {"element": "甲方"}, "高"),
    ("R003", "乙方信息完整", "要素完整性", "element_required", {"element": "乙方"}, "高"),
    ("R004", "合同金额明确", "要素完整性", "element_required", {"element": "合同金额(小写)"}, "高"),
    ("R005", "大写金额存在", "要素完整性", "element_required", {"element": "合同金额(大写)"}, "中"),
    ("R006", "大小写金额一致", "金额审查", "amount_consistent", {}, "高"),
    ("R007", "履行期限明确", "要素完整性", "element_required", {"element": "履行期限"}, "中"),
    ("R008", "付款方式明确", "要素完整性", "element_required", {"element": "付款方式"}, "中"),
    ("R009", "违约责任条款", "条款完整性", "keyword_required", {"keywords": ["违约"]}, "高"),
    ("R010", "争议解决条款", "条款完整性", "keyword_required", {"keywords": ["争议", "纠纷", "仲裁", "诉讼"]}, "中"),
    ("R011", "质保条款", "条款完整性", "keyword_required", {"keywords": ["质保", "保修", "质量保证"]}, "中"),
    ("R012", "验收条款", "条款完整性", "keyword_required", {"keywords": ["验收"]}, "中"),
    ("R013", "保密条款", "条款完整性", "keyword_required", {"keywords": ["保密"]}, "低"),
    ("R014", "知识产权条款", "条款完整性", "keyword_required", {"keywords": ["知识产权"]}, "低"),
    ("R015", "不可抗力条款", "条款完整性", "keyword_required", {"keywords": ["不可抗力"]}, "低"),
    ("R016", "合同生效条款", "条款完整性", "keyword_required", {"keywords": ["生效"]}, "中"),
    ("R017", "签字盖章完整性", "签章审查", "keyword_required", {"keywords": ["盖章", "签章", "公章", "合同专用章"]}, "高"),
    ("R018", "法定代表人/授权代表签字", "签章审查", "keyword_required", {"keywords": ["法定代表人", "授权代表", "委托代理人"]}, "中"),
    ("R019", "签订日期", "签章审查", "regex_required", {"pattern": r"\d{4}\s*年\s*\d{1,2}\s*月|\d{4}-\d{1,2}-\d{1,2}", "message": "未找到签订日期"}, "低"),
    ("R020", "终端单价阈值检查", "金额审查", "amount_max", {"pattern": r"(?:终端|计算机|台式机|笔记本)[^\n]{0,30}?单价[^\n\d]{0,10}([\d,]+(?:\.\d+)?)\s*元", "max": 12000}, "高"),
    ("R021", "单项单价阈值检查", "金额审查", "amount_max", {"pattern": r"单价[^\n\d]{0,10}([\d,]+(?:\.\d+)?)\s*元", "max": 500000}, "中"),
    ("R022", "信创产品合规-禁用非信创CPU", "信创合规", "keyword_forbidden", {"keywords": ["Intel", "英特尔", "AMD 锐龙", "i5-", "i7-"]}, "高"),
    ("R023", "信创产品合规-禁用非国产操作系统", "信创合规", "keyword_forbidden", {"keywords": ["Windows 10", "Windows 11", "Win10", "Win11"]}, "高"),
    ("R024", "信创产品合规-国产化声明", "信创合规", "keyword_required", {"keywords": ["信创", "国产", "麒麟", "统信", "飞腾", "鲲鹏", "海光", "兆芯", "龙芯"]}, "中"),
    ("R025", "禁止无限连带责任", "风险条款", "keyword_forbidden", {"keywords": ["无限连带", "无限责任"]}, "高"),
    ("R026", "禁止单方任意变更", "风险条款", "regex_forbidden", {"pattern": r"乙方有权[^\n。]{0,20}(单方|随时)[^\n。]{0,10}(变更|调整|解除)"}, "高"),
    ("R027", "违约金比例上限", "风险条款", "regex_forbidden", {"pattern": r"违约金[^\n。]{0,20}(?:[3-9]\d|100)\s*%"}, "中"),
    ("R028", "预付款比例检查", "付款审查", "regex_forbidden", {"pattern": r"预付[^\n。]{0,15}(?:[5-9]\d|100)\s*%"}, "中"),
    ("R029", "发票条款", "付款审查", "keyword_required", {"keywords": ["发票"]}, "低"),
    ("R030", "交付地点明确", "条款完整性", "keyword_required", {"keywords": ["交货地点", "交付地点", "实施地点", "送货地点"]}, "低"),
    ("R031", "售后服务响应时间", "条款完整性", "regex_required", {"pattern": r"\d+\s*(?:小时|h|分钟)内?[^\n。]{0,10}(?:响应|到场|上门)", "message": "未约定售后响应时间"}, "低"),
    ("R032", "禁止模糊表述", "文本规范", "keyword_forbidden", {"keywords": ["等等", "原则上", "视情况而定", "另行商定"]}, "低"),
    ("R033", "合同编号存在", "要素完整性", "element_required", {"element": "合同编号"}, "低"),
]

DEFAULT_TEMPLATE_CLAUSES = [
    {"name": "合同标的", "required": True, "keywords": ["标的", "采购内容", "货物清单", "产品清单"]},
    {"name": "合同金额", "required": True, "keywords": ["合同金额", "合同价款", "总价"]},
    {"name": "付款方式", "required": True, "keywords": ["付款", "支付"]},
    {"name": "交付与验收", "required": True, "keywords": ["交付", "交货", "验收"]},
    {"name": "质量保证", "required": True, "keywords": ["质保", "保修", "质量保证"]},
    {"name": "违约责任", "required": True, "keywords": ["违约"]},
    {"name": "保密条款", "required": False, "keywords": ["保密"]},
    {"name": "知识产权", "required": False, "keywords": ["知识产权"]},
    {"name": "不可抗力", "required": False, "keywords": ["不可抗力"]},
    {"name": "争议解决", "required": True, "keywords": ["争议", "纠纷"]},
    {"name": "合同生效", "required": True, "keywords": ["生效"]},
]
