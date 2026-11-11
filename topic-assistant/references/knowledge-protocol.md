# 知识检索、查新与发布（3.0）

## 任务顺序与预算

论文范围与当前专业确认 → 本地学科索引和相关条目 → 未禁用且网络可用时定向查新 → 核验、去重与争议处理 → 增量发布 → 冻结实际用卡/配置 → 完成所选研究模式。每个新的有效阅读、比较、评估、探索和选题任务尝试一次。写作、审校、格式处理、单点解释及同任务工具重试不重复；继续同一范围复用实际记录，范围变化只补新增缺口。技能维护不启动研究查新。

| 本地情况 | 实际查询上限 | 直接来源目标上限（含失败） |
| --- | ---: | ---: |
| 已有相关知识 | 2 | 4 |
| 新学科或当前问题明显缺口 | 4 | 8 |

均计入原 standard 60 分钟/formal 90 分钟，理论、热点、最终可行性共用来源身份去重及最多四篇外部学术全文。足够即停，不以拼接查询绕预算，不为凑数访问。优先原始论文、提出者、出版方及正规机构公开版本；索引题录只作发现/元数据。首次兼顾近期与必要经典，后续按相同专业/问题范围的上次成功时间重叠回溯，默认重叠30天；范围扩大另补。发表日期、实际访问/尝试时间、成功完成时间分别记录，失败不推进成功时间。只查相关修订、边界、反证、更正/撤稿或新应用；新论文不等于新理论。

## 离线与有限失败

`network_status` 为 online/offline/disabled/source-limited；pending 只允许初始化。用户禁网不发外部请求；宿主无联网能力或已确认整体不可用即 offline 并结束，不安装工具、不换镜像、不等恢复。单站失败只标来源受限。断网有适用本地知识则 local-knowledge；缺库、不可读、无适用理论或索引内部修复失败则 paper-only。仅按指定论文阅读、比较和论证，作者使用理论无需对应本地卡；不以记忆补“已核验理论”，不自动收存用户论文或私人材料。

`theory_selection` 保存 status=used/not-used、具体 reason、used_entries（每项 id/version/fit）；paper-only 的 used_entries=[]，不要求主辅理论、mechanism、china_context 或空快照。未使用卡片不成为本次证据；历史 verified_on 不改成本次日期。外部核验待核与本地阅读/比较是否完成分开，缺理论本身不降低成果状态。最终只用一句话说明离线与是否用了本地理论。下一次相关研究或用户要求继续才补查，不后台联网。

`theory_refresh` 保存 status（completed/limited/failed/skipped-offline/skipped-disabled/not-required/reused）、reason、scope、gap、queries、attempts、sources、searched_at、attempted_at、completed_at、previous_success_at、window_start；not-required/reused 另给 reuse_basis。初始化 pending 不能通过最终检查。禁网/离线 queries/attempts/sources=[]、searched_at/completed_at=null；有实际失败探测可在 reason 如实说明，不能记作成功查新。queries 每项 query/searched_at/reviewed_scope；attempts 每项 url/accessed_at/outcome(read/partial/failed)；sources 采用热点同等来源字段与真实读取位置，不能含论文 source_id/evidence_ids。

## 知识结构与发布

知识库固定为实际技能根目录下 knowledge-base/，不依赖 cwd，不扫描桌面/主目录。catalog.json 是唯一有效版本指针；学科 index.json/profile.json 是可重建缓存。entries 下按稳定 ID/vN.json 保存不可变版本；history 保存旧清单；staging 保存未发布候选。应用说明仅实际需要时建立，不复制核心。旧56卡完整原文保存在 migrated entry 的 legacy_markdown，历史日期/来源/类型不提升；旧目录退休前先比字节并建立可恢复归档。

卡片字段由 `knowledge_base.py validate_candidate` 检查：schema_version、id、独立递增 version、中英文名与 aliases（未核英文名须明确未核）、kind、disciplines、概念命题、层级、条件、适用/不适用、竞争解释、author_claims、assistant_guidance、sources、maturity、verification_status、change_basis、review、private_material=false。sources 分别记录 access_level、read_locator、support/support_level、verified_on（真实核验日期）、published_at（发表日期，未知留 null）、accessed_at（实际访问时间，带时区）。旧卡迁移缺少访问时间时可保留 null，不补造历史；新知识必须有实际访问时间。摘要只支持所见有限命题；成熟程度、来源深度、支持强度分开，不把 verified 当全文或全部命题成立。

候选先存 staging；执行者实际读来源、核命题、去重、冲突后才填写 review.status=reviewed 及 reviewer/source_check/dedup_check/conflicts。脚本不代替学术判断。证据不足留候选，不入确定论证；同名异义须 homonym_distinction，相同概念优先原 ID。新应用优先 applications；矛盾保留争议和条件，纠错先核实。没有内容变化不升版，单记查新结果。只保存自写必要摘要与来源定位，不保存用户论文、个人信息、访谈、未公开资料或外部全文缓存。

发布加 O_EXCL 单写锁，检查 expected 旧版本；先写完整不可变新对象，最后原子替换 catalog。锁冲突不重试；中断旧清单仍可用，已提交但索引未写可内部重建。孤立准备版本可在核对后以同内容重试，不覆盖不同内容。清单恢复必须显式指定历史 generation 与当前 expected-generation，验证引用再形成新代；不因存在旧锁自动删锁，确认无活跃写者后才能人工处理。无权限/冲突/失败时研究继续，在运行目录保留 knowledge-proposal.json 与未持久化说明，不静默换知识库位置，不宣称已积累。

## 本地命令与复现

以下脚本路径均相对于实际启用 skill，不依赖调用时 cwd：

```text
python3 <skill>/scripts/knowledge_base.py search "当前问题关键词" --discipline "学科" --limit 4
python3 <skill>/scripts/knowledge_base.py show <稳定ID>
python3 <skill>/scripts/knowledge_base.py profile <配置JSON> [--expected N]
python3 <skill>/scripts/knowledge_base.py stage <候选JSON>
python3 <skill>/scripts/knowledge_base.py publish staging/<候选名>.json [--expected N]
python3 <skill>/scripts/knowledge_base.py application <学科> <稳定ID> <应用JSON> [--expected N]
python3 <skill>/scripts/knowledge_base.py refresh <学科> <问题范围> <查新结果JSON>
python3 <skill>/scripts/knowledge_base.py window <学科> <问题范围>
python3 <skill>/scripts/knowledge_base.py reindex
python3 <skill>/scripts/knowledge_base.py verify
python3 <skill>/scripts/knowledge_base.py recover <历史代数> --expected-generation <当前代数>
python3 <skill>/scripts/validate_run.py freeze-knowledge <运行目录>
```

新增 knowledge schema=1、manifest schema=6、policy_version 为字符串 "3.0"；内容修订号及语言记录 schema 独立。实际选卡及主辅配置复制到 knowledge-snapshot.json 并绑定摘要，设计/报告使用快照而非当前库，后续知识更新不使历史报告失效；修改当前设计或篡改快照仍使审核失效。纯论文无快照。旧任务不得只改版本冒认新验收；合法阅读可在范围仍有效的新任务复用。

正式启用只有一个可写主库：runtime.json.writer_root 指向唯一实际安装根。开发副本指向同一主库时只能读，测试使用隔离临时库。升级用受控部署脚本只同步规则/脚本/测试，默认保留安装库；缺少种子时按稳定 ID/来源/版本逐条合并，不目录覆盖。完整备份可迁移；单独恢复库须先 verify 校验 schema、指针与摘要。程序不会从网络自行改规则、代码、权限或用户约束。
