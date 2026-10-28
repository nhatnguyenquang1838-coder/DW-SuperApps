# DW-SuperApps — W1→W7 Deep Review: Report đối soát duy nhất (DWA tổng hợp)

Ngày: 2026-09-01 · Nguồn: ChatGPT Controller deep review + fanout 5 specialist bot (@taskme, @bmad, @ua, @gwc, @designer) + đối soát code/repo/Jira bởi DWA (read-only).
Trạng thái: READ_ONLY — không mutation, không claim gate PASS.

================================================================
## 0. KẾT LUẬN TỔNG
================================================================
Verdict Controller: CORRECTION_REQUIRED / NOT TERMINAL / NOT CERTIFIED — **ĐƯỢC XÁC NHẬN** bởi toàn bộ fanout (5/5 bot) và đối soát code thật của DWA.

Nhưng root cause thật — mà 5 bot cùng hội tụ (taskme/bmad/ua/gwc/designer) — **không phải 6 lỗi leaf riêng lẻ**:

> **BLOCKER gốc = KHÔNG TỒN TẠI MỘT canonical RuntimePlan model duy nhất xuyên W1–W7.**
> W1 frozen → W3 định nghĩa song song (implementation_plan_ref=None) → W4 compile ra model partial → W5 redefine flat → W6 redefine RunCursor từ đầu.
> Hệ quả: predecessor evidence giữa bất kỳ 2 leaf nào là **không thể verify về mặt cấu trúc** (taskme: "structurally unverifiable"). Đây là DAG blocker, không phải defect riêng lẻ.

================================================================
## 1. ĐỐI SOÁT EVIDENCE (DWA verify trên code thật, đúng SHA)
================================================================
Toàn bộ claim code chính của review ĐỀU KHỚP code thật:

| WP | PR | SHA | Claim review | Đối soát DWA |
|---|---|---|---|---|
| W1 | DW#104 | 99b0d2e6c | terminal transition `if edge.is_terminal: return self` | ✓ runtime_plan.py:299 — xác nhận, không durable state mới |
| W2 | DW#105 | ce8324d0a | `dispatch(context=None)` bypass | ✓ fabric.py:48 — signature `context: StepContext \| None = None` tồn tại, có `dispatch_semantic` riêng |
| W3 | GWC#544 | 0f2ba5b2a | blueprint schema, thiếu canonical producer | ✓ bot gwc verify authority_granted luôn False (blueprint:245-247) |
| W4 | DW#106 | 10a878970 | model fork + compiler thiếu validate raw_edges target | ✓ compiler.py:116-120 validate topology.next NHƯNG 124-130 không check raw_edges[*].target; model W4 = edges/node_binding/... ≠ W2 allowed_inputs/... |
| W5 | GWC#545 | 346382a2b | authority_revalidated=True chỉ vì có authority_id | ✓ bot gwc verify (plan_bound_runtime_executor.py:88-95,106-108) |
| W6 | DW#107 | 854a525aa | CRITICAL: cursor plan A attach plan B | ✓ __init__ (L30-34) chỉ copy plan+cursor, KHÔNG cross-check runtime_plan_ref/revision; `target=="TERMINAL"` uppercase-only (L100); authority_revalidated = allowed!=(read,) (L91-92) |
| W7 | DW#108 | f55375ee9 | in-memory, evidence loose, overwrite, FAIL/PENDING xoá được | ✓ live_certification_harness.py:65-66 (_runs/_branches dict), 115-141 record_verdict overwrite, delete_branch chỉ chặn PASS |

**Control plane:** ✓ mailbox canonical (issue DW#103) vẫn `MATERIALIZING_EXECUTOR_MAILBOX` + executor `WAITING_FOR_COMMAND` — repo đã tới W7/W8 nhưng mailbox chưa materialized = drift hệ thống thật.

**Jira:** ✓ SCRUM-669 = `To Do`; SCRUM-670..676 (W1–W7) = đều `In Review`, chưa terminal receipt; SCRUM-677 (W8) = `In Review` = boundary breach xác nhận.

**Drift SHA duy nhất:** review GPT ghi W8 PR#109 head = `0094a4ed…`, live = `96dc97fb8` — head đã advance. Không làm đổi verdict (W8 vẫn OUT OF SCOPE / FREEZE), nhưng SHA phải cập nhật nếu trích dẫn lại.

================================================================
## 2. VERDICT THEO BOT (fanout 5/5)
================================================================
@taskme (DAG/orchestration):
- Review đúng phần lớn; root cause bị đánh thấp = thiếu canonical model gate W1→W3/W4.
- Correction: canonical model trước; W1→W3→W4 merge tuần tự (từng cái gate), W2/W5/W6/W7 chỉ parallel sau khi W4 verified.
- Review sai ở: "mailbox stuck" KHÔNG phải W6 test gap — là W2 dispatch_semantic bypass khiến executor bỏ qua plan-bound entry.

@bmad (agile):
- Đúng trên leaf đã verify (W3/W5/W6); W1/W2/W4/W7 "plausible, cần verify".
- BỔ SUNG quan trọng: authority_revalidated gap là **SYSTEMIC** (W5 L107 + W6 L91-92 dùng chung stub), không phải lỗi riêng W5.
- Missing: ZERO Acceptance Criteria docs — chỉ có pytest files. Definition of Done cần AC verify được, không chỉ "có test".
- NO W8 cho tới khi W7 real run pass với durable harness evidence.

@ua (impact/arch):
- Đúng cho lane mình: W3↔W4 fork + W5 authority gap là architecture break thật.
- Gap còn thiếu: **evidence traceability** — W7 evidence thiếu linkage tới runtime_plan_digest/step_id; cần evidence digest chain W2 dispatch logs → W6 recovery → W7 harness, nếu không "hard restart" verification không hoàn chỉnh.

@gwc (gate/PR):
- Đúng: W3 authority_granted luôn False, W5 reject authority_granted=True/later_gate_authority=True (đã verify code).
- Review ĐÁNH THẤP W5: "no canonical validator invocation" = BLOCKER vì authority_revalidated là flag trang trí.
- Correction: W5 phải invoke validator thật (validate_research_implementation_bridge.py hoặc tương đương); W6/W7 persist qua NodeEvidenceLedger pattern (.gwc/tasks/<task-id>/node-runtime/ — tools/node_architect/node_evidence_ledger.py đã tồn tại); Draft PRs #104-#107 giữ Draft tới khi exact-head CI SUCCESS + G3 PASS + gwc:g4-authority-receipt.
- Review hơi overstate: W4 compiler không validate edge targets ở compile-time, NHƯNG W5 runtime CÓ validate outcome vs edges (plan_bound_runtime_executor.py:97-103) — là gap compile-time safety, không phải total runtime bypass.

@designer (evidence model/UX của machine-state):
- W7 `evidence: dict[str, Any]` không schema = root cause khiến W6 durable recovery và W5 authority revalidation KHÔNG có output quan sát được, machine-readable.
- Correction: canonical EvidenceRecord dataclass (plan_digest_at_execution, authority_revalidated, readback_digest, expected/actual_output, verdict_reason); append-only idempotent ledger (NodeEvidenceLedger); digest binding mọi nơi; **unified step identity** — W1 RunCursor.step_id / W2 StepContext.step_id / W5 executor.step_id / W6 current_step phải đồng nhất `step_id`.
- Review overstate: W2 dispatch(context=None) gọi là BLOCKER "bypass" — invariant đã được enforce bởi require_semantic_binding() ở W1/W4/W5/W6. Vấn đề thật là StepMaterializer thiếu proof durable TaskController state = durability gap, không phải bypass.

================================================================
## 3. ĐỒNG THUẬN 5/5 (điểm mọi bot đều giữ)
================================================================
1. Một canonical RuntimePlan model duy nhất (freeze W1 primitives + merge W4 branch), enforce ở compile time. — 5/5
2. W3 thành canonical Blueprint producer thật (đọc Flow/Policy/profile/registry), không phải schema trơ; require implementation_plan_ref non-empty. — 5/5
3. authority_revalidated = invoke validator GWC thật (task/repo/branch/head SHA/scope/gate/expiry), áp dụng CHO CẢ W5 LẪN W6 (không chỉ W5). — 5/5
4. W6 cursor constructor phải bind cursor.runtime_plan_ref == plan.runtime_plan_ref AND revision == plan.revision, fail-closed — chặn cross-plan attach. — 5/5
5. Durable store cho cả cursor + TestRun registry (file/JSON/NodeEvidenceLedger), restart phải reconstruct từ durable evidence — không in-memory dict. — 5/5
6. W7: evidence immutable sau record_verdict; require base_sha/head_sha/pr_id/runtime_plan_digest/step_id; ban xoá branch PASS/FAIL/PENDING. — 5/5
7. NO W8 cho tới khi W7 real run pass end-to-end. — 5/5
8. Reconcile GitHub + Jira + SCRUM-669 + Notion + A2A mailbox trước khi resume. — 5/5

================================================================
## 4. ĐIỂM REVIEW SAI / CẦN BỔ SUNG (tổng hợp từ bot)
================================================================
1. (designer + gwc) W2 "dispatch bypass" bị overstate — invariant đã có require_semantic_binding(); nên đổi label thành "durability gap của StepMaterializer", không phải bypass BLOCKER.
2. (gwc) W4 "compiler không validate raw_edges target" là gap compile-time; W5 runtime CÓ validate — review nên nói chính xác hơn.
3. (taskme) Root cause nên dẫn bằng "thiếu canonical model gate" như 1 BLOCKER duy nhất, thay vì 6 defect leaf riêng.
4. (bmad) THIẾU: không có Acceptance Criteria docs — chỉ pytest files; AC phải là Điều kiện Done, không phải "có file test".
5. (ua) THIẾU: evidence traceability chain (W2 dispatch logs → W6 recovery → W7 harness) — thiếu thì "hard restart verification" không hoàn chỉnh.
6. (designer) THIẾU: unified step identity — 4 component đang dùng 4 cách đặt tên step khác nhau.

================================================================
## 5. KẾT LUẬN + HÀNH ĐỘNG ĐỀ XUẤT (chờ Nhat go-ahead)
================================================================
Review Controller: GIỮ NGUYÊN verdict CORRECTION_REQUIRED / NOT TERMINAL / NOT CERTIFIED.
Fanout 5 bot: xác nhận + bổ sung 6 điểm trên, không bot nào bác bỏ verdict.

Correct target trước khi resume W8 — **một integration correction wave** (không tạo 7 helper mới):
  Một canonical RuntimePlan model
    → W3 Blueprint producer thật (đọc registries, implementation_plan_ref non-empty)
    → W4 compiler dùng đúng model đó
    → durable plan + cursor (FilePlanStore/NodeEvidenceLedger, không in-memory)
    → W2 mandatory plan-bound A2A dispatch (đóng đường context=None qua require_semantic_binding)
    → W5 real Node Architect + W5/W6 invoke GWC authority validator thật
    → W6 real cross-component E2E + hard restart (cursor bind ref+revision)
    → W7 durable immutable harness (EvidenceRecord schema, không overwrite, giữ PASS/FAIL history)
    → reconcile GitHub + Jira + SCRUM-669 + Notion + A2A mailbox
  Sau đó mới: W7 PASS → W8 eligible.

W8 = BOUNDARY_BREACH / FREEZE: giữ PR#109 + branch làm evidence; không delete, không merge, không dùng W8 success để retroactive chứng minh W7 PASS. (Lưu ý: head W8 đã advance lên 96dc97fb8.)

================================================================
Evidence: fanout replies tại
/var/folders/yc/shvvmtbd725bw_xfmtd9sc7w0000gn/T/dw_fanout_sgvcb40y/{taskme,bmad,ua,gwc,designer}.reply.md
