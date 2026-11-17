# -*- coding: utf-8 -*-
"""两级分类的第二级：子类别。

一级（AI类别）沿用客户端化之前那 7 个类别，不改、不重算。
这里只在其下再分一层，解决「视频/图集」与「7 个大类」都太粗的问题。

判定是确定性的有序规则（标题 + 话题 + 归纳 + 介绍 + 转写节选），
命中词写进清单的「子类别依据」列，便于逐条复核；不调用任何模型。

顺序即产品判断（AI）：
  1. Skill / Agent 怎么用 —— 方法论优先于资源清单
  2. 开源项目与免费资源
  3. Skill 类（资源清单）
  4. 提示词与模板
  5. 教程与实操 → 测评 → 资讯 → 原理 → 变现
上游若已在行里写了「子类别」，一律尊重上游，不再推断。
"""
import re

AI_SUBS = (
    "开源项目与免费资源",
    "Skill 类",
    "Skill 与 Agent 用法",
    "提示词与模板",
    "教程与实操",
    "工具测评与选型",
    "行业资讯与观点",
    "原理与科普",
    "变现与商业",
    "其他AI相关",
)

NON_AI_SUBS = (
    "知识科普",
    "影视与动漫",
    "娱乐与游戏",
    "音乐与才艺",
    "美食",
    "旅行与城市",
    "健身运动",
    "数码与工具",
    "手工与创作",
    "职场与财经",
    "情感与成长",
    "健康与养生",
    "生活记录",
    "其他",
)

METHOD_RX = re.compile(r"怎么用|怎么|如何|用法|方法论|实操|搭建|配置|调用|编排|工作流|"
                       r"最佳实践|从零|入门|教程|教学|开发|设计|使用", re.I)
SKILL_RX = re.compile(r"skill|skills|技能包|技能库|技能|插件|gpts", re.I)
AGENT_RX = re.compile(r"agent|智能体|mcp|多智能体|multi[- ]?agent", re.I)
OPEN_RX = re.compile(r"开源|open[- ]?source|github|gitee|免费|白嫖|资源合集|合集|"
                     r"素材库|模板库|资源站|导航站|一键部署|本地部署|docker", re.I)
PROMPT_RX = re.compile(r"提示词|prompt|指令|模板", re.I)
TUTOR_RX = re.compile(r"教程|教学|手把手|保姆级|步骤|实战|三分钟|教你|学会|指南|攻略|"
                      r"技巧|建议|布局|交互|实践", re.I)
REVIEW_RX = re.compile(r"测评|评测|对比|横评|选型|哪个好|排行榜|排行|推荐|真实体验|"
                       r"值不值|平替|替代", re.I)
NEWS_RX = re.compile(r"发布|上线|更新|融资|行业|趋势|访谈|对话|观点|解读|报告|新闻|"
                     r"快讯|盘点|发布会", re.I)
THEORY_RX = re.compile(r"原理|科普|为什么|底层|论文|架构|数学|机制|拆解|本质", re.I)
MONEY_RX = re.compile(r"变现|赚钱|副业|接单|流量|私域|商业|带货|电商|获客", re.I)

NON_AI_RULES = (
    ("知识科普", re.compile(r"科普|历史|地理|物理|化学|数学|法律|医学|心理|经济|哲学|"
                            r"冷知识|为什么|原理|解释|语言|文化|英语|学习|书|读书|书评|"
                            r"涨知识", re.I)),
    ("影视与动漫", re.compile(r"影视|电影|动漫|漫画|动画|番剧|解说|短剧|剧情|综艺|预告|片段", re.I)),
    ("娱乐与游戏", re.compile(r"游戏|搞笑|段子|抽象|整活|挑战|沙雕|名场面|明星|爱豆|idol|"
                              r"演唱会|八卦|体育|赛事|球员|nba|漫展|巡演|舞台|专辑|"
                              r"打歌|追星|大赛", re.I)),
    ("音乐与才艺", re.compile(r"音乐|唱歌|声乐|乐器|舞蹈|演奏|翻唱|钢琴|吉他", re.I)),
    ("美食", re.compile(r"美食|做饭|菜谱|探店|厨房|烘焙|小吃|餐厅|火锅|咖啡|寿司|日料|"
                        r"烧烤|面馆|家常菜", re.I)),
    ("旅行与城市", re.compile(r"旅行|旅游|攻略|自驾|露营|徒步|风景|民宿|酒店|citywalk|"
                              r"地标|商场|城市|开业|同城", re.I)),
    ("健身运动", re.compile(r"健身|训练|增肌|减脂|跑步|瑜伽|篮球|足球|羽毛球|游泳|拉伸", re.I)),
    ("数码与工具", re.compile(r"手机|电脑|相机|镜头|耳机|显卡|硬件|开箱|装机|平板|手表|"
                              r"路由器|软件|工具|格式转换|开源|免费|api|网站推荐|app|"
                              r"应用推荐|便签|windows|win11|微软|c盘|anc|配件|理线", re.I)),
    ("手工与创作", re.compile(r"手工|手作|拼豆|图纸|绘画|画画|摄影|写作|书法|黏土|编织|"
                              r"设计|配色|排版|ui|前端|海报|画册|ppt", re.I)),
    ("职场与财经", re.compile(r"职场|面试|简历|管理|创业|销售|沟通|办公|理财|银行|信用卡|"
                              r"利息|保险|消费|存钱|社畜|公司|互联网|股票|基金|涨停|投资|"
                              r"网贷|贷款|房产|生意|金融|经济", re.I)),
    ("情感与成长", re.compile(r"恋爱|情感|婚姻|成长|思维|认知|命运|修心|人际|逆袭|智慧", re.I)),
    ("健康与养生", re.compile(r"健康|养生|营养|医生|疾病|减肥|睡眠|中医|体检|保健|蔬菜", re.I)),
    ("生活记录", re.compile(r"vlog|日常|生活|记录|家庭|亲子|萌宠|宠物|装修|收纳|穿搭|请假|"
                            r"晚霞|日落|护肤|个护|口喷", re.I)),
)


def _text_of(row, transcript=""):
    bits = [
        str(row.get("标题/文案") or ""),
        str(row.get("话题标签") or ""),
        str(row.get("核心内容归纳") or ""),
        str(row.get("内容介绍") or ""),
        str(row.get("AI类别") or ""),
        str(transcript or "")[:800],
    ]
    return " \n ".join(b for b in bits if b)


def _hits(rx, text, limit=4):
    out = []
    for m in rx.finditer(text):
        token = m.group(0)
        if token and token not in out:
            out.append(token)
        if len(out) >= limit:
            break
    return out


def _result(name, hits):
    hits = [h for h in hits if h]
    conf = "高" if len(hits) >= 2 else ("中" if hits else "低")
    return {"子类别": name, "依据": "、".join(hits[:6]), "置信度": conf}


def classify(row, transcript=""):
    """返回 {子类别, 依据, 置信度}。"""
    upstream = str(row.get("子类别") or "").strip()
    if upstream:
        return {"子类别": upstream, "依据": "上游标注", "置信度": "高"}

    text = _text_of(row, transcript)
    ai = str(row.get("AI相关") or "").strip() == "是"

    if ai:
        skill = _hits(SKILL_RX, text)
        agent = _hits(AGENT_RX, text)
        method = _hits(METHOD_RX, text)
        # 1) 方法论：Skill/Agent 与「怎么用」同时出现
        if (skill or agent) and method:
            return _result("Skill 与 Agent 用法", (skill + agent)[:2] + method[:2])
        # 2) Skill 类（资源清单）—— 明确提到 Skill/Agent 时，比“开源/合集”更具体
        if skill or agent:
            return _result("Skill 类", (skill + agent))
        # 3) 开源与免费资源
        opened = _hits(OPEN_RX, text)
        if opened:
            return _result("开源项目与免费资源", opened)
        # 4) 提示词与模板
        prompt = _hits(PROMPT_RX, text)
        if prompt:
            return _result("提示词与模板", prompt)
        # 5) 教程 / 6) 测评 / 7) 资讯 / 8) 原理 / 9) 变现
        for name, rx in (("教程与实操", TUTOR_RX), ("工具测评与选型", REVIEW_RX),
                         ("行业资讯与观点", NEWS_RX), ("原理与科普", THEORY_RX),
                         ("变现与商业", MONEY_RX)):
            found = _hits(rx, text)
            if found:
                return _result(name, found)
        return _result("其他AI相关", [])

    for name, rx in NON_AI_RULES:
        found = _hits(rx, text)
        if found:
            return _result(name, found)
    return _result("其他", [])
