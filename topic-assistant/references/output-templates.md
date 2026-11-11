# 产物与交接约定

仅记录本次实际需要的阶段；单个问题直接回答，不建立整套产物。机器记录用 UTF-8 JSON，正文用自然中文，结构正确不能替代内容审核。事实维护一份，中间可读稿按需派生。

## 目录与状态

`validate_run.py init <论文文件夹上一级> --source-dir <论文文件夹绝对路径> --mode topic|full|read|compare|evaluate|explore` 为需要持久记录的任务创建唯一目录、manifest.json、research-direction.md、references.json 和 cards/extraction 目录。运行目录必须位于指定论文文件夹的直接父目录，因此与论文文件夹平级；最终 Markdown 保存在该唯一运行目录内。多个用户明确指定的目录可重复 `--source-dir`，但必须具有同一父目录。未提供目录、路径不是绝对路径、目录不存在、父目录不一致或传入的输出父目录不是论文文件夹上一级时必须停止；没有写入权限时请求权限，不得回退到其他位置。standard 选题用 `topic`；`full` 必须在 `constraints.formal_trigger` 保存用户要求正式成品的原话。manifest 固定记录 `policy_version`、`source_scope: provided-only`、非空 `allowed_input_roots`、`output_scope: source-parent`、`output_root`、`literature_review_policy: required|waived`、`literature_review_waiver` 、`external_hotspot_scope: shared-preselection` 和 `external_feasibility_scope: final-shortlist-only`。默认 required；waived 必须保存用户明确放弃综述的原话。不创建通用 search-log.json；最终候选联网核验只用 web-feasibility.json。新任务隔离，同一任务继续仅可使用与当前允许目录及输出父目录一致的运行记录。

新运行 manifest schema_version=6，保留 policy_version（字符串 "3.0"）、run_id、created_at（带时区）、mode、constraints（direction_original、source_scope、allowed_input_roots、output_scope、output_root、literature_review_policy、literature_review_waiver、external_hotspot_scope、external_feasibility_scope、formal_trigger、exclusions、degree、deadline、resources、changes）、rules、capabilities、inputs、artifacts、report。未知用 null，但 source_scope、allowed_input_roots、output_scope、output_root、literature_review_policy、external_hotspot_scope 和 external_feasibility_scope 不得为空。output_root 必须是全部允许论文文件夹共同的直接父目录，也必须是当前运行目录的直接父目录。literature_review_policy 默认 required；只有用户明确要求不写综述、只要题名或提纲时才改为 waived，并把用户原话写入 literature_review_waiver。read/compare/explore 可以只交付阶段结果、report=null；topic/full/evaluate 最终要求报告。旧 schema=2/3/4/5 不能只改版本继续新验收；确认已有用户指定范围仍适用后新建运行，可复用范围内已核阅读记录，不要求无意义地重读或再次授权。

每个 inputs 条目：input_id、source_id、path、sha256、total_pages、extraction_path、card_path；重复文件可加 duplicate_of，版本可加 version_relation。path 必须是 `allowed_input_roots` 中某一目录或其子目录内源文件的绝对真实路径，符号链接解析后也不得越界；产物路径只能是运行目录内相对路径。字节重复仍登记每个 input_id，可关联同一 source_id，各卡片注明复用原因。

每个 artifacts 条目：artifact_id、path、version（正整数）、status（pending/complete/limited/failed/stale）、reason、depends_on（实际消耗的 artifact_id:version），以及 stamp 登记的 sha256、fingerprint_version、source_dependencies（source_id:内容摘要）、context_sha256（选题/可行性/报告所用约束与规则摘要，其余为 null）。登记实际存在的来源台账和阶段结果；所有 JSON 顶层须有 version。complete/limited 需真实文件，limited/failed 解释原因。

schema=6 必需阶段边：综合→本次卡片；热点无候选/报告下游依赖；选题→综合（没有则卡片）及热点；可行性→选题；最终联网→可行性；最终稿→已生成的综合/热点/选题/可行性/联网记录。最终联网结论回写可行性只更新该记录版本，web 依赖更新后的版本；可行性不反向依赖 web，避免循环。论文台账不作所有卡片整包版本依赖；按实际 source_id/source_ids/closest_sources 提取细粒度摘要。外部来源用 web_id，不能进入论文引用依赖。stamp 另登记 theory_dependencies，只绑定实际用卡，未用卡变更不使阅读成果失效。

更新流程：保留需要恢复的旧版本 → 定点修改并增加产物 version（JSON 内容与清单一致） → 审核实际受影响部分，更新依赖版本和状态 → `stamp <目录>` → `check <目录>`。stamp 对同版本内容变化直接拒绝；对未升版且所用来源/依赖变化的产物及其下游标 stale，不自动批准。原已 stale 的记录必须经协调者重审、升版并修改状态后才能通过。stamp 只登记完整性，不证明语义正确。源 PDF、抽取快照及已交付成品不覆盖；运行中的清单/台账/草稿可受控更新，最终交付使用新文件名。重验次数、唯一一次上游回退及 complete/limited/blocked/checkpointed 终态遵守 [有限执行策略](execution-policy.md)，不得为了消除 stale 无限升版。

## 卡片最小结构

```json
{
  "input_id": "P001", "source_id": "S001", "version": 1,
  "reading_state": "只读到一部分", "read_pages": [1],
  "unread": [{"pages": [2,3], "reason": "全文尚未阅读"}],
  "coverage_note": "仅第一页摘要，不能评价正文设计及完整结果",
  "fields": {
    "purpose": {"value": "摘要实际所见的研究问题", "evidence_ids": ["E001"]},
    "design": {"value": null, "missing_reason": "当前未读到", "evidence_ids": []},
    "results": {"value": null, "missing_reason": "当前未读到", "evidence_ids": []}
  },
  "evidence": [{
    "evidence_id": "E001", "source_id": "S001", "claim": "具体主张",
    "observed": "实际读到的内容", "pages": [1], "locator": "摘要",
    "attribution": "author", "access_level": "abstract", "limitations": "仅摘要"
  }]
}
```

完整分析的 fields 涵盖目的、理论/概念、对象/情境、资料、设计、分析、结果、作者局限/空白及读者评议；持久卡片核心键 purpose/design/results 必须存在，缺项用真实原因。四种 missing_reason：原文未说明/当前未读到/识别不清/不适用。四种 reading_state 如例；未能读取/未读取的 read_pages 为空，已读完须覆盖全部页及相关图表附录。read_pages 中未读完整的页列 partial_pages，已读完不得含此项。coverage_note 说明真实覆盖。单页只读摘要也记部分阅读；轻任务不必为满足本卡片结构补读无关部分。

复用卡片时记录 reused_from（原运行/卡片、文件 SHA-256、原阅读与本次核对范围）及 coverage_note；继续使用已有完整记录即可，不复制出第二套相同证据 ID。进入不同运行需重新登记稳定关联并避免 ID 冲突，不增加独立支持数。新增主张超出原阅读或证据时才补读。

evidence_id 全运行唯一。pages 是该来源对应文件实际读过的物理页序；无页码时可为空，但 locator 必须可定位。证据来源文件必须位于 `allowed_input_roots`；不得把网页、目录外文件或模型记忆写入 references.json 冒充本次证据。

## 来源台账 references.json

顶层 version、sources 与 evidence 数组。每个来源必须对应 inputs 中位于允许目录内的文件，并记录 source_id、title、authors（数组）、year、type、publication、volume、issue、pages_or_article、doi、url、accessed_at、version_note、language、access_level（metadata/abstract/fulltext）、verified（条目已核布尔值）、required_fields（按类型/目标体例应有字段）、missing_fields（未核或缺失字段名）。被最终报告引用的来源还须有 metadata_verification：`{method,locator,checked_at,checked_fields,observed}`；method 只用 pdf-title-page 或 pdf-title-and-end-pages，observed 保存从允许目录内原文件实际核对的著录字段。页码须从题名页/末页核对，不得用 PDF 页数推算，不得访问 URL 或外部权威条目补齐。不得用空 required_fields 假装无需著录；正式引用至少 title/authors/year/publication，缺失项如实标记，不伪造。

同 DOI/版本不重复建来源；版本关系不清不能只凭题名合并。仅 metadata 不支撑研究发现。formal-ready 与条目 verified 不等同：摘要来源可支持摘要实际所述，关键全文判断仍需正文。

## 综合、本地核对与选题

synthesis.json：version、purpose_coverage、conclusion_coverage、groups（数组）、matrix（数组）、limitations（说明或数组）均必需。两类 coverage 为 `{input_id,status,reason}` 数组；status=included/excluded/unknown，每个输入恰好一次，非 included 给理由；确无可比材料可空组/矩阵但解释限制。

本 skill 不创建或接受通用 search-log.json。目录内查找只用于定位已登记输入，证据仍通过 source_ids 和 evidence_ids 关联；若运行目录出现 search-log.json，校验失败。最终联网核验必须使用下述专用文件，不得借机扩大检索用途。

topics.json：version、formed_at（带时区，不早于热点 checked_at）、topics 数组；零题用 reason 说明。保留 topic_id、title、唯一 question、contribution_type、planned_contribution、gap_state、checked_at、closest_sources、counterevidence_note、source_ids、evidence_ids、空 search_ids、conditions。gap_state 仍仅 local_question/candidate/covered/unverified。

每题增加下列结构。候选写简明事实，不先写长综述；不合格题仅保留必要问题与资格原因，不再展开设计：

- scope：按学科路由选择。公共管理经验/制度文本用 region/population/setting/time_window/unit/basis；其他类型及其他学科用 object/boundary/unit/basis。共同保存 basis_type（user/local-evidence/verified-public/anonymized）及 selection（fixed、units、basis）。不适用地域不填占位。
- qualification：status=eligible/ineligible、reason、checks。3.0 通用 checks 为 scope/single_problem/problem_basis/disciplinary_fit/contribution；公共管理再核 ai_boundary/decision_relevance。问题不成立不能靠 draft 保留，缺外部理论本身不否决。
- problem_basis 保存 type（reported/policy-risk/user-stated/hypothesis）与 basis；公共管理政务 AI 另记 ai_boundary，其他学科不受政务边界限制。
- theory 可为空或省略。确实用外部知识时 primary、可选 secondary（至多一个不同ID）、分工 division，以及 fit/observables/method_fit/alternative/limits；实际机制、中国情境仅适用时写。ID/version/source/fit 必须与 theory_selection 和冻结快照相符。无卡或纯论文改写 disciplinary_basis，说明本次论文实际概念、论证或方法依据，不强填理论/机制。
- 公共管理应用题 decision 保留 actor/lever/expected_answer/evaluation/conditions/alternative_result；其他学科 contribution 使用 new_knowledge/validation/limits。closure 通用判断按下述3.0补充，不强填管理决策。
- source_ids/evidence_ids 只指指定论文；search_ids=[]；hotspot_ids 只指实际线索，没有关联写 hotspot_limitation。

feasibility.json 保存 version、assessments，逐题恰好一条 assessment：topic_id、direction（符合/部分符合/不符合/暂无法判断）、direction_reason、verdict（建议做/调整后再做/不建议做/暂无法判断）、reason、resources、design、conditions（数组）、unresolved（数组）。用户研究方向未知时 direction 只能为暂无法判断。design 按实际研究类型说明资料、前提、方法和验证办法；每个实际已核资源记录 access_level（entry/documentation/sample/acquired）、location、checked_at、fit、limitations，不把入口可见写成样本已取得。

同一文件的 selection 保存 eligible_topic_ids、ineligible_reasons（题 ID→理由）、ranked_topic_ids、selected_topic_ids 和 ranking_reason。排序仅覆盖合格题一次，暂定名单取其前五或更少；零题也登记空名单与原因。联网后的资格否决写 post_verification_exclusions，不抹去原暂定名单；最终题只能从暂定名单中保留或重排，不补位。详细资格、排序与交接规则见 [可行性筛选](agent-3-feasibility.md)。

## 共享热点 hotspots.json

只在最终选题流程新增此一份记录，不生成逐刊/逐理论运行日志。顶层：version、purpose=`shared-preselection`、status（complete/limited/unavailable）、reason、cutoff_date（执行日 YYYY-MM-DD）、started_at/checked_at（带时区）、categories、queries、attempts、sources、signals、academic_fulltext（complete/limited/unavailable）、academic_reason。必要核验受限时 report=draft，仍交付实际成果。

categories 使用 manifest.discipline.hotspot_categories；公共管理为 governance/policy/academic-cn/academic-intl 四键，每项 `{status:checked|limited|unavailable,finding}`。完成检索未发现新增内容可 checked，finding 说明范围与零结果；checked 必须有相应查询。queries 每项 `{category,query,searched_at,reviewed_scope}`，最多六项、每项一条实际查询。attempts 每项 `{url,accessed_at,outcome:read|partial|failed}`，最多十二项，包括失败与替代入口；时间均在 started_at—checked_at 之间，阶段不超过十二分钟。

sources 每项 `web_id,title,url,source_type,accessed_at,access_level,observed,limitations,published_at,date_basis`。source_type 为 policy/governance/academic/agenda 等明确类型；access_level 据实际为 landing-page/metadata/abstract/partial/document/fulltext；published_at 为日期或 null，date_basis=publication/online-first/unknown。元数据未知如实留空，访问日期不能替代发表日期。source_type=academic 时另记 journal、article_version、read_locator、fulltext_available、fulltext_opened、complete_text；前三项为真实说明，后三项布尔值，全文已读需 available/opened/complete_text 都为 true。全文可取得但没读，access_level 仍填实际层级；省略注释不标 fulltext。可选 cache_path 仅指运行目录内实际存在的外部缓存，不是输入论文。

signals 每项 `{hotspot_id,claim,relevance,web_ids,time_role}`；web_ids 指向实际读过来源，time_role=recent/background/unknown，日期未知不能标 recent。正文只写实际支持的线索；持续热点还须独立依据，不能以转载凑数。academic_fulltext=complete 至少有一篇相关、实际已读的完整论文；没有则 limited/unavailable 并说明缺口，不假称中外均全文覆盖。

## 最终联网可行性 web-feasibility.json

最终推荐的 selected_topic_ids 非空时建立，空时不执行。顶层 version、purpose=`final-feasibility-only`、status（complete/limited/unavailable）、checked_at（带时区）、topic_ids（必须等于 selection.selected_topic_ids）、final_topic_ids（其子集，可按最终可行性重排）、reason、results；不从淘汰项补位。

results 对 topic_ids 每题一项：topic_id、status（confirmed/conditional/not_feasible/unavailable）、checks、searches、attempts、reused_hotspot_sources、conclusion、effect_on_verdict、unresolved。checks 含 research_overlap/resource_access/current_context/implementation_blockers 四项实际说明；effect_on_verdict 只用建议做/调整后再做/不建议做/暂无法判断。attempts 和 reused_hotspot_sources 必须显式登记数组，空时填 []。attempts 格式同热点，每题最多三个目标；reused_hotspot_sources 为 `{web_id,supports}` 数组，只引用已核热点来源并说明用途，实际足够时 searches 可为空。

每题 searches 最多 2 项，每项保存 purpose、query、searched_at（带时区）、reviewed_scope、sources。sources 为数组，每项保存 title、HTTP(S) url、source_type、accessed_at（带时区）、access_level（landing-page/metadata/abstract/partial/document/fulltext）、observed、limitations，不得含 source_id。学术来源另登记与热点相同的版本、实际阅读位置、可得/已读/完整全文状态和发表日期；理论查新、热点、最终可行性合计最多展开四篇学术全文。直接打开的 URL 必须登记 attempts，失败也计入。没有直接来源时数组可空，但 reviewed_scope 必须如实说明实际检查范围，不能写成零结果证明。limited/unavailable 必须有顶层 reason；unavailable 的各题结果原则上为 unavailable，只有基于已读本地材料并登记 post_verification_exclusions 的后续否决可为 not_feasible，须说明依据来自本地审核，整体仍为 unavailable，不得冒称联网确认。complete 要求每题至少一个实际读到内容的直接来源（含有效复用；失败访问、目录页和元数据不计）、不得含 unavailable 结果，final_topic_ids 恰好包含全部 confirmed/conditional 并排除 not_feasible。结果状态与 effect_on_verdict 必须相容：confirmed 对应建议做/调整后再做，conditional 对应调整后再做/暂无法判断，not_feasible 对应不建议做，unavailable 对应暂无法判断。

网页来源只支持选题可行性说明，不得复制进 references.json、bibliography、逐题综述 source_ids/evidence_ids、resources 或必读文献表。核验结果须同步回写 feasibility.json 对应 assessment 的 verdict、reason 和 unresolved，人工确认没有相互冲突的新旧判断；网页访问细节只在 web-feasibility.json 维护。校验器检查结构、范围和交接，不能证明网页判断真实或来源质量充分。

## 最终报告

topic-report 与 formal-proposal 的读者可见结构必须使用 [Markdown 成品模板](report-template.md)，并登记 `template_version: markdown-report-v3`。该模板固定报告外壳、状态披露、章节顺序和内部信息清理；不固定综述主题与论述内容。凡报告保留最终选题，standard 与 formal 都须逐题写综述，格式、学术论述与交付边界只以 [PDF 综述写法](literature-review.md) 为准，不另创问答式综述格式。证据不足时交“待补证综述稿”，不得省略。只有用户明确豁免并保存原话，或最终为0题，才可使用 `literature_review: none`。0题用原因和补证建议替代空章节。read/compare/explore 可直接交付阶段结果，不为通过校验凑正式报告。

标题使用一个 `#` 总标题，主体同级章节统一 `##`，逐题或主题子节依次用 `###`、`####` 等，不跳级。具体主题标题由文献内容决定，上述仅用于保持 Markdown 结构清楚，不是另创综述格式。参考文献标题与其所属层级匹配；独立综述文章采用 R25—27 的完整文章结构，论文内综述不另加署名/摘要/关键词。

逐题书目和报告统一书目都从同一台账及同一体例派生；逐题只列其正文实际引用条目，不复制整份必读表。可以在逐题综述末设置较低层级的“参考文献”，统一书目仍用 `## 参考文献`；同一报告编号必须全局唯一，不能每题从 [1] 重启后指向不同文献。若交付独立编号的逐题文档，分别登记并验收，不能在一个报告混用。

报告及阶段选题交付最多呈现 5 个题，只能呈现 web-feasibility.json.final_topic_ids 并保持其顺序；正文、总表、附录和聊天均不附本地或联网阶段淘汰的题及候补名单。零暂定题时无 web 文件，使用已登记的空名单。清理淘汰题的章节及仅为其服务的引用、书目、必读说明，并同步引用编号和清单后，才创建语言审校快照。输入材料的处理附录可以保留阅读覆盖，但不得借其展开淘汰选题。

manifest.report 记录 markdown、document_type（topic-report/formal-proposal/review-article）、template_version（选题报告固定为 markdown-report-v3）、literature_review（none/per-topic/article）、topic_ids、feasibility_verification、hotspot_verification、academic_fulltext（热点与学术全文为 complete/limited/unavailable；可行性通常同此三值，仅零暂定题时为 not-applicable）、citation_style、reference_style、reference_style_basis、bibliography（source_id、label、entry）、citations（source_id、token、locator）、recommended_source_ids、status（draft/formal-ready）、review（semantic、language 及说明）。独立综述文章另记录真实 `author`；未知时不能编造，且不得标为 formal-ready。有暂定题时 topic_ids 和 feasibility_verification 必须分别等于 web-feasibility.json 的 final_topic_ids 和 status；零暂定题不执行最终联网核验、不要求联网文件，feasibility_verification 必须为 not-applicable，报告说明未执行及原因。热点与全文状态必须与 hotspots.json 一致；limited/unavailable 时报告只能是 draft，并在正文中明确外部可行性待核。有最终选题且未获用户明确豁免的 topic-report/formal-proposal 必须用 `per-topic`；独立综述文章用 `article`。`none` 仅允许0题或 constraints 中有用户原话支持的 waived。markdown 必须是运行目录内最终报告的相对路径。数字体例 label 用不带括号的 1、2 等；token 用正文真实形式如 [1]；作者年份 token 如 (张某, 2024)。entry 必须从台账生成并与正文书目相同；不同 token 的 source_id 映射不能冲突。采用正式体例时必须用 `reference_style_basis` 记录目标模板或现行标准的版本和选择依据；若使用已被现行版本替代的旧引用标准，还必须记录 `reference_style_confirmed_by_user: true`。

`reference_style=basic` 只用于待核草稿的可读基础著录，不宣称逐条符合任何国标。正式交付先采用目标院校/期刊体例；没有目标体例时选择一个当前适用的国家标准引用体系，不默认偏向作者—年份制，并写明 `reference_style_basis`。用 `validate_run.py reference-data <运行目录>` 查看台账生成的 basic_entry 和 metadata_sha256。实际体例用明确名称作 reference_style，每个引用来源增加 formatted_reference：`{style,text,metadata_sha256}`，text 是人工核对所选体例后的条目，摘要哈希来自该命令。元数据改变会使自定义条目失效，必须重核后更新哈希，不能仅更改哈希冒称重核。校验器会比较来源、条目和报告，不再允许台账题名变化而书目静默不变。

课程数字要求不自动启用。需要时在 rules 加用户已确认的对象，例如 `{enabled:true,confirmed_by_user:true,source:"实际课程要求 T35",document_type:"formal-proposal",min_references:50,recent_min_count:50,recent_years:5,as_of_year:2026,foreign_min_ratio:0.3333333333,title_max_chars:25,title_count_mode:"han"}`。只配置真实适用字段，不能自动套用本例；窗口采用指定年度及前 N-1 个自然年。外文比例需 language 有依据。草稿报告缺口警告，formal-ready 未达标报错；题名计数口径必须指定 han（汉字）或 all（全部字符）。

校验脚本按各级精确名为“参考文献”或“References”的标题识别书目，至同级或更高标题结束；书目中的编号不算正文引用，附录与必读表另设标题。数字引用支持 [1]、[1,2]、[1-3]、中文逗号，按正文首次出现顺序从 [1] 连续编号；合写时也按组内出现顺序核对，重复引用不重新编号。citations 逐来源用规范 token [1]、[2] 登记，即使正文合写 [1,2]。逐题书目为全局编号子集，可以有编号缺口，不能误判为首次顺序错误。作者年份需维护完整 token 台账并人工检查遗漏。不得把脚本不识别的体例冒称已自动验收。

formal-ready 要实际语义审核和全文语言审校通过、正式引用条目核实完整且无 stale。综述按 PDF 要求核结构、比较、述评、复制完整性及证据，在现有 review 说明中记录核过的题和缺项，不另建重复审核。draft 允许准确说明来源缺项和未验收，但不允许悬空引用、捏造或虚记完成；报告为 draft 不妨碍其中某段已合格，但只有实际通过综述验收的具体部分才可称可复制使用。

## Markdown 交付前的语言审校记录

任何模式实际交付最终报告时，先按 [全文语言审校](humanize-academic.md) 完成一次全文编辑。review_language.py prepare 自动建立 language-review.json 及同名 .before.md 原稿快照；记录 schema_version=2，包含 version、原稿/规则摘要、非空行单元及其位置、reviewed_units、issues、protected_terms、六项 checks、reviewer、reviewer_type、human_reviewer、status、最终文件摘要和完成时间，并增加下述 literature 内容验收，以及实际入选题/所用理论卡的 design_context_sha256 和 design_protected_terms。范围或本次冻结的已用知识发生变化时原记录失效；知识库后续更新及未用卡变化不触发重审。prepare 不代表审校完成；旧 schema=1 不可直接批准新稿，须按新规则建立记录，不能只改版本号。

### 同一记录中的逐题综述验收

literature 包含 applicable（必须实际填写 true/false）、reason、sources_path（默认 references.json，须在当前运行目录）、citation_style、reference_style、reference_style_basis、sections。prepare 根据最终入选题、document_type 和 constraints 中的综述策略初始化验收：有最终入选题且策略为 required 时，standard 与 formal 都按题初始化为 pending；独立综述文章初始化 review；仅在最终零选题或用户明确 waived 时生成 applicable=false、具体 reason 和空 sections。不得用 report.literature_review: none 绕过 required，也不得把 standard 当作省略综述的理由。

sections 顺序须与 report.topic_ids 相同；最终选题必须显式登记冻结名单，不能因不足五题取全部候选。独立综述用 review。每项字段：topic_id；status=pending/ready/limited；body_lines=[起始行,终止行]；reference_lines=[起始行,终止行]；source_ids；evidence_ids；notice；checks。行范围是最终 Markdown 的 1 基闭区间，正文及本题书目不交叠；综述正文不得包含“本题的问题与贡献”“研究设计/实施路径”“可行性/条件/风险/降级方案”等选题报告内容，这些部分须置于 body_lines 之外。书目范围首行为独立的“参考文献”标题，随后每条独占一个段落。checks 为 pdf_structure、source_selection、comparison_and_critique、evidence_and_scope、standalone_prose、reference_format 六项，只能根据实际审核填写，不以自动全选充作内容审阅。

ready 要求六项均通过，且已在指定目录内实际核对来源的代表性、一次文献优先、新近性和不同观点覆盖；目录材料不足则保持 limited。正文须有真实主题小标题及连贯论述、对应正文引文、恰为本题所引的书目，evidence_ids 关联已有卡片/来源台账中实际读到且可定位的证据。reference_style 不得用 basic 冒充正式体例；按现有 formatted_reference 约定核定目标体例，或在没有目标模板时核定所选当前适用国家标准，并以 `reference_style_basis` 记录依据后绑定元数据摘要。不能杜撰字号等课件未规定的强制数值。

独立综述文章除上述内容验收外，还须具有一个文章题名、真实作者署名、指示性摘要、3—5 个关键词、引言、按内容命名的主题主体和参考文献；收束段必须完成归纳、评论和展望功能，但短篇可不单列“结语”标题。作者未知的草稿必须说明限制，不得编造，也不得标为 formal-ready。该完整前后结构只适用于 `review-article`，不得反向要求逐题综述或论文内部综述重复署名、摘要和关键词。

limited 是明确的待补证交付，不得宣称可直接使用；notice 必须包含“待补证综述稿”和具体缺项，原样出现在该题正文外，不能只在内部记录里标状态。仍须正确引用实际可支持的内容与对应书目。pending、漏题、范围失效、错误引文或把未核书目标 ready 时，seal/check 均拦截。

独立编辑综述 Markdown 而没有完整运行记录时，也可沿用此审校记录：在同目录提供实际来源台账，在 literature 中登记相同格式的 citations 和 bibliography；不强制补选题、查新和可行性流水线。无 manifest 时 prepare 不猜适用性，执行者据真实交付内容填写。已登记报告则直接复用 report.citations/bibliography，不抄出第二套台账。

封存除绑定最终正文外，也登记 literature_context_sha256：仅涵盖本次所用来源、证据、引用体例及入选题；所用资料变化须重新核受影响内容并建立新记录，新增无关来源不触发全文重读。此摘要只防验收与资料脱节，不证明证据的学术质量。

协调者实际通读全部文字、修改并处理每个候选/人工问题后填写记录；未改的清楚段落只需覆盖声明，不另造评语。seal 核完整覆盖、逐项处理、改动登记和机械可核的保真项，并绑定 final 的当前字节；不能证明真实通读或所有语义均正确。正文应在 prepare 前冻结；有效封存记录不能靠再次 seal 给变化稿件续批。只有 critical 错误且全任务尚未使用唯一一次上游回退时，才可修订正文并用一个新记录审校，不能为普通措辞或 Markdown 格式问题连续建立记录。审校源稿覆盖表格、题注、附录和其他拟输出文字；保护区也查看但不作风格改写。

manifest.report.review 增加 `language:{status:"passed",record:"language-review.json"}`，record 使用运行目录内相对路径。凡登记最终报告，check 都会核其有效性；缺失、未封存、覆盖不足或 final.md 在审校后变化均会报错。审校台账是内部执行记录，不自动塞进正文或要求用户阅读。

推荐顺序：一次共享热点 → 短设计与候选资格审核（不足五题也筛选）→ 合格题按本地可行性排序取暂定前 5 → 最终联网核验及一次实质复核 → `preflight` → 冻结 final_topic_ids 并形成报告、同步引用 → 一次完成内容/引用/综述核对并冻结正文 → prepare → 一次全文语言编辑和一次修改处保真复核 → final 必要升版 → seal/check 审校 → 更新 manifest 语言记录与最终引用位置 → stamp → `check` → 按结果交付。每个校验最多首次加一次定点修复后复查。

preflight 是写长稿前对已有记录的轻量检查，不要求 final.md、语言记录或内容指纹，也不读取原论文。check 的退出码为 0 才表示该次自动检查通过；输出额外提供 delivery.validation、state 和 markdown：存在实际报告时返回其绝对路径，通过草稿为 checked-draft，通过正式稿为 checked-formal，失败但文件存在为 unvalidated-draft，未生成文件为 no-report。该输出不写新验收文件、不自动修改状态或正文。失败时按执行策略交未验收草稿并明确问题，不能把路径、stamp、seal 或自报 passed 当成通过；宿主可使用退出码，但 skill 不假定其强制调用。

## 最后人工复核

核对：主张与证据深度/位置；综述综合而非堆摘要；本地与领域边界；最近似研究与反证；创新类型/假设；方向原话；资料与方法/个人条件；返修后各处一致；规范适用；引用/书目/必读清单分开；Markdown 标题层级、表格和链接可读。review 中记录做了什么和未完成什么，不能用结构通过代替这些判断。

## 3.0 运行与纯论文补充

manifest schema_version=6、policy_version="3.0"；另登记 discipline、network_status、knowledge_mode、theory_selection、theory_refresh，完整字段与枚举见[知识协议](knowledge-protocol.md)。init 增加 --discipline、--research-type、--network；pending 仅初始化合法，交付前填写实际状态。新研究即使仅阅读/比较也尝试理论查新；写作、审校及同任务继续复用。旧schema=5亦须新建运行后复用合法阅读，不能只改版本。

确实用卡时运行 freeze-knowledge，冻结主辅学科配置、所用卡版本/来源及适配说明到 knowledge-snapshot.json；无卡不生成空快照。theory_dependencies 基于本次快照，后续知识库更新不会让历史报告失效；本次设计改变仍要复核。纯论文没有主辅理论也能通过准入及审校，作者论文中使用理论无需另卡。

closure.research_value 用 known_answer/open_question/new_knowledge/disciplinary_basis（用卡时可用 theory_use）；question_status 仍为 requires-analysis。inference_level 增加 proof/design/interpretation/normative，required_form 增加 proof/construction/argument/interpretive-corpus。observables 可表示命题、论证前提、构造或解释文本，按实际材料填写，不能造实证字段。其他学科用 contribution_links 代替 decision_links；各项 observable_ids/condition/action/basis/applicability 不变，action 表示条件成立时的知识判断或构造结果。纯论文不强填 mechanism/china_context。

离线/禁网的热点、最终核验保留 unavailable 与具体待核原因、空查询访问记录，日期为本次登记时间而非检索成功时间。需要当期外部核验的选题保留 draft 与待核说明；本地阅读/比较是否完成独立判定，不因缺理论自动降级。标准最多五题、逐题综述及用户原话豁免、Markdown与全文语言审校继续生效。
