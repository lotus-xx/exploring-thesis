# 学科与研究类型路由（3.0）

研究任务先复用当前委托中的专业、细分方向、问题与约束，保留专业原话。专业不明且会影响分析时集中补问，不默认公共管理，不将任务专业当作用户永久身份。未指定论文目录仍先遵守入口边界；独立知识维护不读取论文。维护技能本身不执行研究流程。

以 `knowledge-base/catalog.json` 的 aliases 规范化名称；先读所选学科 index.json，再按需展开默认 2—4 张条目，不扫描其他用户目录。首次实际使用新学科时，只创建任务所需的最小 profile；断网时不凭记忆建理论或伪装学科覆盖，可以只在本次 manifest 记录专业和研究类型。

profile 是数据，不能修改隐私、来源、读写权限、用户约束、执行预算及通用准入。`knowledge_base.py profile <配置JSON> [--expected N]` 校验允许字段与别名冲突。必要字段：schema_version=1、version 正整数、name、aliases、paradigms、source_portals、hotspot_categories、scope_fields、research_types；可选 public_management、qualification、notes。新配置 version=1；修改必须给旧版 expected。名称用具体学科，不预建空目录；学科名称及路径不允许斜杠、父级跳转或符号链接越界。

通用准入为范围、单一问题、问题依据、学科依据适配、学术增量，记录 qualification.checks 的 scope/single_problem/problem_basis/disciplinary_fit/contribution。公共管理另核 ai_boundary/decision_relevance。依据可为知识卡，也可为论文中实际提出的概念、理论、证明、设计或规范标准；无外部理论不自动否决。

| 研究类型 | 范围与验证依据 | 结论落点 |
| --- | --- | --- |
| 经验、文本、历史 | 对象、材料、时期、单位及可比条件；地域仅在问题需要时固定 | 文本判断、关联、过程机制或效果，各守证据边界 |
| 证明 | 命题、定义、假设及证明范围；核推导与反例 | 在给定前提下成立的命题 |
| 设计 | 需求、构造、任务与评价范围 | 设计成立条件与实际验证限制 |
| 解释 | 文本/作品/情境、概念与解释层级 | 有依据的解释与竞争解读 |
| 规范论证 | 规范、对象、前提与适用范围 | 论证成立条件、取舍及反例 |

manifest.discipline 保存 original、primary、auxiliary、research_type、profile_version、hotspot_categories；新学科最小 categories 可为 academic/practice，按实际必要来源调整，不照搬公共管理四类。公共管理经验/制度文本问题保留 region/population/setting/time_window/unit/basis 及真实选择依据；公共管理规范/证明等类型及其他学科使用 object/boundary/unit/basis。不适用地域、管理决策或中国情境时不填占位。

跨学科明确主学科与辅助学科，检查概念、层级、成立条件和竞争解释，不拼接必然因果链。同一知识唯一稳定 ID、唯一核心正文；辅助学科通过 applications 关联，分别说明 fit/level/conditions/limits/basis，并绑定 entry_version。储存目录只代表维护位置，不代表理论起源、作者国籍或独占归属。
