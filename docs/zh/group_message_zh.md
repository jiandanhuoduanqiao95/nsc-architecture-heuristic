# 群消息模板（中文参考副本 / group message, Chinese reference copy）

> **Non-submitted reference.** The English version in `docs/HANDOFF_A.md`
> is authoritative; this Chinese copy exists only for the team chat and is
> never submitted.

```
@B @C 角色 A 已交接：tag a-scorer-handoff.3（历史标记 a-scorer-v1 / v1.1 / final / a-scorer-handoff / a-scorer-handoff.1 / a-scorer-handoff.2 不再移动）。
先看 docs/milestone_runbook.md：B 按 B1–B6 跑（α/β 网格用 variants/dev_alpha_*、variants/m3_beta_*；α*/β* 用 tools/select_alpha.py；六方法 1,000 次导出 results/selection_1000.json，契约在 docs/interface.md；失败案例用 tools/selection_failures.py）。
C：先决定作者邮箱再推公开远端（runbook C0）；4 页素材在 docs/report_pack.md（每个数字有来源，三个 [[B: …]] 待 B 填）；图在 docs/figures/；freeze 模板 docs/freeze_template.json；约定草案 docs/CONVENTIONS_draft.md 待签。
验收：checks/run_checks.py --no-write → 18/18；--mutations → 7/7；单测全过；check_starter PASS。
不要改 student_score.py 的 ALPHA（冻结时由 C 改并写 freeze.json，CH18 --freeze 校验）；--split final 只在 freeze tag 之后由 B 跑一次。
```
