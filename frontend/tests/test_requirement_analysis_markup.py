import unittest
from pathlib import Path


INDEX_HTML = (
    Path(__file__).resolve().parents[1] / "public" / "index.html"
).read_text(encoding="utf-8")


class RequirementAnalysisMarkupTests(unittest.TestCase):
    def test_requirement_analysis_navigation_and_workspace_regions_exist(self) -> None:
        # 需求解析收敛进工作台方案标签；旧路由重定向到 workspace?tab=plan。
        self.assertIn('{ page: "workspace", label: "项目工作台", id: currentProjectId }', INDEX_HTML)
        self.assertIn("LEGACY_PAGE_REDIRECTS", INDEX_HTML)
        self.assertIn('requirements: { page: "workspace", tab: "plan" }', INDEX_HTML)
        self.assertIn('id="requirementChatForm"', INDEX_HTML)
        self.assertIn('id="requirementFileInput"', INDEX_HTML)
        self.assertIn('id="requirementChatStream"', INDEX_HTML)
        self.assertIn('id="requirementMarkdownPreview"', INDEX_HTML)

    def test_requirement_upload_accepts_markdown_files(self) -> None:
        self.assertIn('accept=".pdf,.doc,.docx,.txt,.md,text/plain,text/markdown,application/pdf"', INDEX_HTML)
        self.assertIn("PDF / Word / TXT / MD", INDEX_HTML)

    def test_requirement_analysis_uses_result_and_thinking_tabs(self) -> None:
        self.assertIn("requirement-result-tabs", INDEX_HTML)
        self.assertIn('id: "analysis", label: "解析结果"', INDEX_HTML)
        self.assertIn('id: "plan", label: "实施方案"', INDEX_HTML)
        self.assertIn('id: "thinking", label: "思考过程"', INDEX_HTML)
        thinking_index = INDEX_HTML.index('id: "thinking", label: "思考过程"')
        analysis_index = INDEX_HTML.index('id: "analysis", label: "解析结果"')
        plan_index = INDEX_HTML.index('id: "plan", label: "实施方案"')
        self.assertLess(thinking_index, analysis_index)
        self.assertLess(thinking_index, plan_index)
        self.assertNotIn('label: "解析结果.md"', INDEX_HTML)
        self.assertNotIn('label: "实施方案.md"', INDEX_HTML)
        self.assertNotIn('id: "process", label: "执行过程"', INDEX_HTML)
        self.assertNotIn('id: "versions", label: "版本记录"', INDEX_HTML)
        self.assertNotIn('id: "exports", label: "导出记录"', INDEX_HTML)
        self.assertIn("data-requirement-tab", INDEX_HTML)
        self.assertIn('id="requirementVersionSelect"', INDEX_HTML)

    def test_requirement_workspace_is_named_workspace(self) -> None:
        self.assertIn('<h2>工作区</h2>', INDEX_HTML)
        self.assertNotIn('<div class="nav-title">结果工作区</div>', INDEX_HTML)
        self.assertNotIn('<h2>Markdown 预览</h2>', INDEX_HTML)

    def test_requirement_analysis_has_api_helpers_for_tasks_chat_and_export(self) -> None:
        self.assertIn("function renderRequirementAnalysis", INDEX_HTML)
        self.assertIn("function buildPendingRequirementTask", INDEX_HTML)
        self.assertIn("function buildPendingRequirementMessageTask", INDEX_HTML)
        self.assertIn("function createRequirementTask", INDEX_HTML)
        self.assertIn("function sendRequirementMessage", INDEX_HTML)
        self.assertIn("function exportCurrentRequirementDocument", INDEX_HTML)

    def test_requirement_assistant_is_named_xiao_p(self) -> None:
        self.assertIn("小P 对话", INDEX_HTML)
        self.assertIn("小P 执行过程", INDEX_HTML)
        self.assertIn('message.role === "assistant" ? "小P" : "用户"', INDEX_HTML)
        self.assertIn("function renderMessageUsedSkills", INDEX_HTML)
        self.assertIn("chat-skill-badge", INDEX_HTML)
        self.assertGreater(INDEX_HTML.count("renderMessageUsedSkills(message)"), 1)
        self.assertNotIn("LLM 对话", INDEX_HTML)
        self.assertNotIn("LLM 执行过程", INDEX_HTML)

    def test_requirement_markdown_preview_uses_real_markdown_renderer(self) -> None:
        self.assertIn("marked.min.js", INDEX_HTML)
        self.assertIn("purify.min.js", INDEX_HTML)
        self.assertIn("function renderMarkdownPreview", INDEX_HTML)
        self.assertIn("marked.parse", INDEX_HTML)
        self.assertIn("DOMPurify.sanitize", INDEX_HTML)
        self.assertIn('class="markdown-preview" id="requirementMarkdownPreview"', INDEX_HTML)
        self.assertIn("${markdownPreview}", INDEX_HTML)
        self.assertNotIn("<pre class=\"markdown-preview\" id=\"requirementMarkdownPreview\">${escapeHtml(markdown)}</pre>", INDEX_HTML)

    def test_requirement_upload_shows_pending_progress_before_api_returns(self) -> None:
        self.assertIn('status: "processing"', INDEX_HTML)
        self.assertIn('status: "in_progress"', INDEX_HTML)
        self.assertIn('state.activeRequirementTask = buildPendingRequirementTask(file.name, file.type);', INDEX_HTML)
        self.assertIn("async function runRequirementSkillSteps", INDEX_HTML)
        self.assertIn('/run-next-step', INDEX_HTML)
        self.assertIn("function getRequirementStepIcon", INDEX_HTML)
        self.assertIn("function getRequirementStepClass", INDEX_HTML)
        self.assertNotIn("导出准备", INDEX_HTML)

    def test_requirement_export_supports_md_docx_pdf(self) -> None:
        self.assertIn('id="requirementExportFormat"', INDEX_HTML)
        self.assertIn('<option value="md">Markdown (.md)</option>', INDEX_HTML)
        self.assertIn('<option value="docx">Word (.docx)</option>', INDEX_HTML)
        self.assertIn('<option value="pdf">PDF (.pdf)</option>', INDEX_HTML)
        self.assertIn("html-docx.js", INDEX_HTML)
        self.assertIn("html2pdf.bundle.min.js", INDEX_HTML)
        self.assertIn("window.htmlDocx.asBlob", INDEX_HTML)
        self.assertIn("window.html2pdf()", INDEX_HTML)
        self.assertIn(".docx`", INDEX_HTML)
        self.assertIn(".pdf`", INDEX_HTML)

    def test_requirement_parsing_streams_into_document_tabs(self) -> None:
        # 解析开始时默认展示“解析结果”，而不是空的“思考过程”。
        self.assertIn(
            'state.activeRequirementTask = buildPendingRequirementTask(file.name, file.type);\n'
            '        state.requirementActiveTab = "analysis";',
            INDEX_HTML,
        )
        # 每个步骤开始时根据技能切到对应文档 tab，让正文边生成边渲染。
        self.assertIn(
            'state.requirementActiveTab = state.requirementStream.target;',
            INDEX_HTML,
        )

    def test_requirement_stream_only_renders_into_its_target_tab(self) -> None:
        # 流式缓冲带 target 标记，避免方案流式时串台到解析结果页。
        self.assertIn('reasoning: "", content: "", target: "analysis"', INDEX_HTML)
        self.assertIn('reasoning: "", content: "", target: "plan"', INDEX_HTML)
        self.assertIn(
            'state.requirementStream.target = event.skill === "generate_plan" ? "plan" : "analysis";',
            INDEX_HTML,
        )
        self.assertIn(
            'else if (state.requirementActiveTab === stream.target)',
            INDEX_HTML,
        )
        self.assertIn(
            'else if (state.requirementStream && state.requirementActiveTab === state.requirementStream.target)',
            INDEX_HTML,
        )

    def test_requirement_uses_sse_streaming_for_skill_execution(self) -> None:
        self.assertIn("async function streamRequirement", INDEX_HTML)
        self.assertIn("response.body.getReader()", INDEX_HTML)
        self.assertIn("new TextDecoder()", INDEX_HTML)
        self.assertIn('event.type === "reasoning"', INDEX_HTML)
        self.assertIn('event.type === "content"', INDEX_HTML)
        self.assertIn('event.type === "done"', INDEX_HTML)
        self.assertIn("function updateRequirementStreamingView", INDEX_HTML)
        self.assertIn("requirementStream: null", INDEX_HTML)
        self.assertIn("streamRequirement(`/api/requirement-tasks/${currentTask.id}/run-next-step`", INDEX_HTML)
        self.assertIn("streamRequirement(`/api/requirement-tasks/${currentTask.id}/messages`", INDEX_HTML)

    def test_requirement_has_model_selector_and_no_prompt_chips(self) -> None:
        # 旧的快捷标签已移除。
        self.assertNotIn('class="prompt-chips"', INDEX_HTML)
        self.assertNotIn("data-prompt=", INDEX_HTML)
        # 新的模型下拉框，含两个模型选项，并把所选模型透传给后端。
        self.assertIn('id="requirementModelSelect"', INDEX_HTML)
        self.assertIn('value="gpt-5.5-medium-fast"', INDEX_HTML)
        self.assertIn('value="deepseek"', INDEX_HTML)
        self.assertIn('requirementModel: "gpt-5.5-medium-fast"', INDEX_HTML)
        self.assertIn("state.requirementModel = event.target.value", INDEX_HTML)
        self.assertIn("{ model: state.requirementModel }", INDEX_HTML)
        self.assertIn("{ message, model: state.requirementModel }", INDEX_HTML)

    def test_requirement_export_uses_clean_final_version(self) -> None:
        # 导出走专用取值函数，取最终版本干净内容，不使用 diff 高亮视图。
        self.assertIn("function getRequirementExportMarkdown", INDEX_HTML)
        self.assertIn("const markdown = getRequirementExportMarkdown(task);", INDEX_HTML)
        self.assertIn("const latestVersion = (activeDocument.versions || [])[0];", INDEX_HTML)
        export_fn_start = INDEX_HTML.index("async function exportCurrentRequirementDocument")
        export_fn = INDEX_HTML[export_fn_start:export_fn_start + 1600]
        self.assertNotIn("renderMarkdownDiffPreview", export_fn)

    def test_requirement_upload_has_abort_button_while_processing(self) -> None:
        self.assertIn("requirementAbortRequested: false", INDEX_HTML)
        self.assertIn("function cancelRequirementProcessing", INDEX_HTML)
        self.assertIn("function buildTerminatedRequirementTask", INDEX_HTML)
        self.assertIn('id="requirementAbortButton"', INDEX_HTML)
        self.assertIn("终止", INDEX_HTML)
        self.assertIn("state.requirementAbortRequested", INDEX_HTML)

    def test_requirement_thinking_tab_shows_hidden_reasoning_chain(self) -> None:
        self.assertIn('if (state.requirementActiveTab === "thinking")', INDEX_HTML)
        self.assertIn("function renderRequirementThinkingMarkdown", INDEX_HTML)
        self.assertIn("小P思考过程", INDEX_HTML)
        self.assertIn("documents.analysis?.reasoning", INDEX_HTML)
        self.assertIn("documents.plan?.reasoning", INDEX_HTML)
        self.assertNotIn("不展示模型内部隐藏推理链路", INDEX_HTML)

    def test_requirement_chat_streams_optimization_live(self) -> None:
        self.assertIn("optimizationPending: true", INDEX_HTML)
        self.assertIn("正在理解修改要求...", INDEX_HTML)
        self.assertIn("buildPendingRequirementMessageTask(state.activeRequirementTask, message)", INDEX_HTML)
        self.assertNotIn("setRequirementOptimizationStage", INDEX_HTML)
        self.assertIn("updateRequirementStreamingView();", INDEX_HTML)

    def test_requirement_plan_can_highlight_changes_between_versions(self) -> None:
        self.assertIn("requirementHighlightChanges: true", INDEX_HTML)
        self.assertIn("function getPreviousRequirementVersion", INDEX_HTML)
        self.assertIn("function renderMarkdownDiffPreview", INDEX_HTML)
        self.assertIn("markdown-diff-added", INDEX_HTML)
        self.assertIn("markdown-diff-removed", INDEX_HTML)
        self.assertIn("id=\"toggleRequirementDiffButton\"", INDEX_HTML)
        self.assertIn("高亮修改", INDEX_HTML)
        self.assertIn("正常预览", INDEX_HTML)

    def test_requirement_conversation_hides_automatic_upload_messages(self) -> None:
        self.assertIn("function isAutomaticRequirementMessage", INDEX_HTML)
        self.assertIn(".filter((message) => !isAutomaticRequirementMessage(message))", INDEX_HTML)
        self.assertIn('content.startsWith("已上传：")', INDEX_HTML)
        self.assertIn('content === "已完成读取文档、解析任务和生成方案。"', INDEX_HTML)
        self.assertIn('content === "正在解析需求文档，请稍候。"', INDEX_HTML)

    def test_requirement_analysis_does_not_shadow_browser_document(self) -> None:
        self.assertNotIn("const document = getRequirementDocument(task);", INDEX_HTML)

    def test_requirement_analysis_layout_is_compact_and_prevents_overlap(self) -> None:
        self.assertIn("grid-template-columns: minmax(280px, 320px) minmax(420px, 1fr);", INDEX_HTML)
        self.assertIn(".requirement-workspace .page-card", INDEX_HTML)
        self.assertIn("min-width: 0;", INDEX_HTML)
        self.assertIn(".requirement-chat-panel h2", INDEX_HTML)
        self.assertIn("font-size: 18px;", INDEX_HTML)
        self.assertIn("@media (max-width: 1360px)", INDEX_HTML)
        self.assertIn(".requirement-chat-panel", INDEX_HTML)
        self.assertIn("grid-template-rows: auto minmax(0, 1fr) auto;", INDEX_HTML)
        self.assertIn(".requirement-upload-row", INDEX_HTML)

    def test_requirement_workspace_uses_viewport_height_for_inner_scroll(self) -> None:
        # 工作区用确定的视口高度，使右侧结果面板内部滚动而不是整页变长。
        self.assertIn("height: calc(100vh - 96px);", INDEX_HTML)
        self.assertIn("min-height: min(620px, calc(100vh - 128px));", INDEX_HTML)
        self.assertNotIn("height: min(760px, calc(100vh - 128px));", INDEX_HTML)
        self.assertIn("align-items: stretch;", INDEX_HTML)
        self.assertIn(".requirement-results {\n      display: grid;\n      grid-template-rows: auto auto minmax(0, 1fr);", INDEX_HTML)
        self.assertIn(".markdown-preview", INDEX_HTML)
        self.assertIn("min-height: 0;", INDEX_HTML)
        self.assertIn("overflow: auto;", INDEX_HTML)

    def test_requirement_model_select_row_has_bottom_spacing(self) -> None:
        # 模型下拉与下方输入行之间留出间距，不再贴边。
        self.assertIn(".model-select-row {", INDEX_HTML)
        self.assertIn("margin-bottom: 8px;", INDEX_HTML)

    def test_requirement_document_supports_inline_edit_mode(self) -> None:
        # 可编辑 Markdown 模式：进入编辑显示 textarea，保存调用 /versions 接口存为新版本。
        self.assertIn('id="editRequirementButton"', INDEX_HTML)
        self.assertIn('id="requirementEditArea"', INDEX_HTML)
        self.assertIn('class="markdown-editor"', INDEX_HTML)
        self.assertIn("saveRequirementEditedVersion", INDEX_HTML)
        self.assertIn("/versions", INDEX_HTML)
        self.assertIn("state.requirementEditMode", INDEX_HTML)

    def test_requirement_chat_input_fills_available_row_width(self) -> None:
        self.assertIn(".chat-input-row input", INDEX_HTML)
        self.assertIn("flex: 1 1 auto;", INDEX_HTML)
        self.assertIn("width: 100%;", INDEX_HTML)
        self.assertIn(".chat-input-row .button-secondary", INDEX_HTML)
        self.assertIn("flex: 0 0 auto;", INDEX_HTML)

    def test_requirement_analysis_removes_placeholder_explanatory_copy(self) -> None:
        self.assertNotIn("上传、解析进度、方案优化都在同一个对话流里。", INDEX_HTML)
        self.assertNotIn("第一版会读取可抽取文本并生成模拟方案。", INDEX_HTML)
        self.assertNotIn("上传需求文档后，我会在这里显示读取文档、解析任务、生成方案和导出准备的过程。", INDEX_HTML)

    def test_requirement_analysis_header_does_not_show_backend_status(self) -> None:
        self.assertIn("renderRequirementHeader", INDEX_HTML)
        self.assertNotIn('class="requirement-page-header">\n          ${renderPageHeader', INDEX_HTML)


class ProjectExecutionMarkupTests(unittest.TestCase):
    def test_execution_nav_and_routing_registered(self) -> None:
        # 建模/模拟计算为独立工作台标签；旧 execution 路由重定向到 workspace?tab=modeling。
        self.assertIn('id: "modeling", label: "建模"', INDEX_HTML)
        self.assertIn('id: "computation", label: "模拟计算"', INDEX_HTML)
        self.assertIn('execution: { page: "workspace", tab: "modeling" }', INDEX_HTML)
        self.assertIn("renderExecutionPage", INDEX_HTML)
        self.assertIn("renderComputationPage", INDEX_HTML)
        self.assertIn("loadExecutionData", INDEX_HTML)

    def test_execution_entry_button_after_plan(self) -> None:
        self.assertIn('id="enterExecutionButton"', INDEX_HTML)
        self.assertIn("enterProjectExecution", INDEX_HTML)
        self.assertIn('switchWorkspaceTab("modeling")', INDEX_HTML)

    def test_execution_uses_molstar_viewer(self) -> None:
        self.assertIn("molstar@4/build/viewer/molstar.js", INDEX_HTML)
        self.assertIn("molstar@4/build/viewer/molstar.css", INDEX_HTML)
        self.assertIn('id="molstarViewer"', INDEX_HTML)
        self.assertIn("loadStructureFromData", INDEX_HTML)
        self.assertIn("initExecutionViewer", INDEX_HTML)

    def test_execution_links_requirement_plan_and_analysis(self) -> None:
        # 工作台内方案子步骤与建模/计算页共享需求与执行上下文。
        self.assertIn("state.executionRequirement", INDEX_HTML)
        self.assertIn("renderPlanSubsteps", INDEX_HTML)
        self.assertIn("data-plan-sub", INDEX_HTML)
        self.assertIn("ensureWorkspaceExecution", INDEX_HTML)
        self.assertIn("loadPlanDocument", INDEX_HTML)
        self.assertIn("getComputationSpec", INDEX_HTML)
        self.assertIn("/api/requirement-tasks/${requirementTaskId}", INDEX_HTML)

    def test_execution_keeps_optimization_chat_without_manual_stages(self) -> None:
        # 全自动建模：保留对话框供后续继续优化，但移除旧的分阶段手动建模 UI。
        self.assertIn('id="executionModelSelect"', INDEX_HTML)
        self.assertIn("state.executionModel", INDEX_HTML)
        self.assertIn('id="executionChatForm"', INDEX_HTML)
        self.assertIn("sendModelingMessage", INDEX_HTML)
        self.assertIn("/modeling-chat", INDEX_HTML)
        self.assertNotIn("data-execution-stage", INDEX_HTML)
        self.assertNotIn("data-spec-block", INDEX_HTML)

    def test_modeling_chat_uses_single_scrollable_chat_panel(self) -> None:
        self.assertNotIn("modeling-chat-collapse", INDEX_HTML)
        self.assertNotIn("<summary>建模对话</summary>", INDEX_HTML)
        self.assertIn('id="executionChatStream"', INDEX_HTML)
        self.assertIn("overflow-y: auto;", INDEX_HTML)
        self.assertIn("overscroll-behavior: contain;", INDEX_HTML)
        self.assertIn(".execution-chat-stream", INDEX_HTML)
        self.assertIn('class="chat-stream execution-chat-stream" id="executionChatStream"', INDEX_HTML)

    def test_structure_preview_can_switch_molecule_and_system(self) -> None:
        # 右侧结构预览可在单个分子与完整体系之间切换查看。
        self.assertIn('id="executionStructureSelect"', INDEX_HTML)
        self.assertIn("getExecutionStructures", INDEX_HTML)
        self.assertIn("getActiveExecutionStructure", INDEX_HTML)
        self.assertIn("state.executionStructureView", INDEX_HTML)
        self.assertIn("完整体系", INDEX_HTML)

    def test_plan_shows_modeling_spec_and_autogenerates(self) -> None:
        # 实施方案页渲染「建模规划」小节，并在方案生成/优化后自动抽取。
        self.assertIn("renderRequirementSpecBlock", INDEX_HTML)
        self.assertIn("modelingSpecMarkdown", INDEX_HTML)
        self.assertIn("## 建模规划", INDEX_HTML)
        self.assertIn("ensureRequirementModelingSpec", INDEX_HTML)
        self.assertIn("/modeling-spec", INDEX_HTML)
        self.assertIn("state.requirementSpecLoading", INDEX_HTML)

    def test_execution_has_one_click_auto_modeling(self) -> None:
        # 一键自动建模：读规划→逐个建分子→组装，全程流式编排。
        self.assertIn('id="autoModelingButton"', INDEX_HTML)
        self.assertIn("自动建模", INDEX_HTML)
        self.assertIn("startAutoModeling", INDEX_HTML)
        self.assertIn("/auto-modeling", INDEX_HTML)
        self.assertIn("state.executionAutoRunning", INDEX_HTML)
        self.assertIn('streamEvent.type === "progress"', INDEX_HTML)

    def test_modeling_can_enter_computation_with_model_input(self) -> None:
        self.assertIn('id="enterComputationButton"', INDEX_HTML)
        self.assertIn("进入模拟计算", INDEX_HTML)
        self.assertIn("enterComputationFromModeling", INDEX_HTML)
        self.assertIn("/computation/prepare", INDEX_HTML)
        self.assertIn("modelInput", INDEX_HTML)
        self.assertIn("renderComputationModelInput", INDEX_HTML)
        self.assertIn("currentExecutionHasSystem", INDEX_HTML)
        self.assertIn('switchWorkspaceTab("computation")', INDEX_HTML)

    def test_modeling_progress_shows_used_skills(self) -> None:
        self.assertIn("function renderModelingUsedSkills", INDEX_HTML)
        self.assertIn("建模使用的 Skills", INDEX_HTML)
        self.assertIn("modeling.usedSkills", INDEX_HTML)

    def test_execution_auto_generates_modeling_spec(self) -> None:
        # 执行页进入后自动从方案抽取建模规划，供自动建模使用。
        self.assertIn("getExecutionModelingSpec", INDEX_HTML)
        self.assertIn("ensureExecutionModelingSpec", INDEX_HTML)
        self.assertIn("maybeGenerateExecutionSpec", INDEX_HTML)


class ProjectWorkspaceMarkupTests(unittest.TestCase):
    def test_workspace_route_and_loader_registered(self) -> None:
        # 工作台作为以项目为主线的入口：路由、聚合加载、首屏分发。
        self.assertIn('currentPage === "workspace"', INDEX_HTML)
        self.assertIn("renderWorkspacePage", INDEX_HTML)
        self.assertIn("loadWorkspaceData", INDEX_HTML)
        self.assertIn("/workspace", INDEX_HTML)
        self.assertIn('id="workspaceBody"', INDEX_HTML)

    def test_workspace_has_stage_stepper(self) -> None:
        # 顶部贯穿式阶段进度条，按数据派生当前阶段，且可点击跳转。
        self.assertIn("computeWorkspaceStages", INDEX_HTML)
        self.assertIn("workspace-progress", INDEX_HTML)
        self.assertIn("renderWorkspaceProgress", INDEX_HTML)
        self.assertIn("data-workspace-step-tab", INDEX_HTML)
        self.assertIn("renderWorkspaceHeader", INDEX_HTML)

    def test_workspace_has_project_dropdown(self) -> None:
        # 顶部项目下拉切换。
        self.assertIn('id="workspaceProjectSelect"', INDEX_HTML)
        self.assertIn("renderWorkspaceProjectOptions", INDEX_HTML)

    def test_create_project_is_modal(self) -> None:
        # 新建项目改为弹窗，且概览不再重复展示阶段进度/交付清单。
        self.assertIn('id="createProjectModal"', INDEX_HTML)
        self.assertIn("openCreateProjectModal", INDEX_HTML)
        self.assertIn("bindCreateProjectForm", INDEX_HTML)
        self.assertIn("modal-overlay", INDEX_HTML)

    def test_checklist_uses_dropdown(self) -> None:
        # 交付清单状态改为下拉菜单。
        self.assertIn("check-status-select", INDEX_HTML)
        self.assertIn('select[data-check-name]', INDEX_HTML)

    def test_execution_has_simulation_computation_step(self) -> None:
        # 建模之后新增「模拟计算」步骤：标签页、开始按钮、SSE 编排。
        self.assertIn('id: "computation", label: "模拟计算"', INDEX_HTML)
        self.assertIn("renderExecutionComputationPane", INDEX_HTML)
        self.assertIn("startComputation", INDEX_HTML)
        self.assertIn('id="computationRunButton"', INDEX_HTML)
        self.assertIn("/api/executions/${execution.id}/run-computation", INDEX_HTML)

    def test_create_removed_from_sidebar_nav(self) -> None:
        # 左侧导航不再含「新建项目」，仅保留仪表盘/列表/工作台。
        nav_block = INDEX_HTML.split("const navItems = [", 1)[1].split("];", 1)[0]
        self.assertNotIn('page: "create"', nav_block)
        self.assertIn('page: "dashboard"', nav_block)
        self.assertIn('page: "workspace"', nav_block)

    def test_overview_has_editable_project_form(self) -> None:
        # 概览 Tab 合并项目维护表单，交付清单留在交付 Tab。
        self.assertIn("renderProjectInfoReadonly", INDEX_HTML)
        self.assertIn("info-grid", INDEX_HTML)
        overview_block = INDEX_HTML.split("function renderWorkspaceOverview()", 1)[1].split("function ", 1)[0]
        self.assertIn("renderProjectMaintenanceStack", overview_block)
        self.assertIn("bindProjectDetailEvents", overview_block)
        self.assertNotIn("renderProjectDeliveryStack", overview_block)

    def test_workspace_has_five_tabs_with_plan_substeps(self) -> None:
        # 方案 Tab 内含需求解析/方案确认子步骤；建模与模拟计算独立 Tab。
        self.assertIn('data-workspace-tab', INDEX_HTML)
        self.assertIn("switchWorkspaceTab", INDEX_HTML)
        tab_block = INDEX_HTML.split("const workspaceTabDefs = [", 1)[1].split("];", 1)[0]
        self.assertIn('label: "方案"', tab_block)
        self.assertNotIn('需求解析', tab_block)
        self.assertNotIn('实施方案', tab_block)
        for tab_id in ("overview", "plan", "modeling", "computation", "delivery"):
            self.assertIn(f'id: "{tab_id}"', tab_block)
        self.assertNotIn('id: "requirement"', tab_block)
        self.assertNotIn('id: "execution"', tab_block)
        self.assertIn("plan-substeps", INDEX_HTML)
        self.assertIn("renderPlanSubsteps", INDEX_HTML)

    def test_computation_step_shows_used_skills(self) -> None:
        self.assertIn("function renderStepUsedSkills", INDEX_HTML)
        self.assertIn("使用的 Skills", INDEX_HTML)
        self.assertIn("step.usedSkills", INDEX_HTML)

    def test_computation_steps_can_run_with_runner_selection_and_artifacts(self) -> None:
        self.assertIn("computationDefaultRunner", INDEX_HTML)
        self.assertIn("computationPendingRuns", INDEX_HTML)
        self.assertIn('id="computationDefaultRunnerSelect"', INDEX_HTML)
        self.assertIn('id="computationStepRunnerSelect"', INDEX_HTML)
        self.assertIn('id="computationRunStepButton"', INDEX_HTML)
        self.assertIn('id="computationRunAllButton"', INDEX_HTML)
        self.assertIn("cursor-cli", INDEX_HTML)
        self.assertIn("正在调用 cursor-cli", INDEX_HTML)
        self.assertIn("buildPendingComputationRun", INDEX_HTML)
        self.assertIn("await refreshFullExecution(execution.id);", INDEX_HTML)
        self.assertIn("computation-log", INDEX_HTML)
        self.assertIn("runComputationStep", INDEX_HTML)
        self.assertIn("terminateComputationStep", INDEX_HTML)
        self.assertIn("runAllComputationSteps", INDEX_HTML)
        self.assertIn("postJson(`/api/executions/${execution.id}/computation/steps/${encodeURIComponent(stepId)}/run`", INDEX_HTML)
        self.assertIn("postJson(`/api/executions/${execution.id}/computation/steps/${encodeURIComponent(stepId)}/terminate`", INDEX_HTML)
        self.assertIn("postJson(`/api/executions/${execution.id}/computation/run-all`", INDEX_HTML)
        self.assertIn("/computation/steps/${encodeURIComponent(stepId)}/run", INDEX_HTML)
        self.assertIn("/computation/steps/${encodeURIComponent(stepId)}/terminate", INDEX_HTML)
        self.assertIn("/computation/run-all", INDEX_HTML)
        self.assertIn('id="computationTerminateStepButton"', INDEX_HTML)
        self.assertIn("/computation/artifacts/${encodeURIComponent(artifact.id)}", INDEX_HTML)
        self.assertIn("renderComputationRunResult", INDEX_HTML)
        self.assertIn("apiBaseUrl", INDEX_HTML)
        self.assertNotIn("API_BASE", INDEX_HTML)

    def test_computation_refresh_restores_active_step_from_runs(self) -> None:
        self.assertIn("const module = getComputationModule(state.activeExecution);", INDEX_HTML)
        self.assertIn("const currentStepId = steps.some((step) => step.id === module.currentStepId) ? module.currentStepId : \"\";", INDEX_HTML)
        self.assertIn("const firstRunStepId = steps.find((step) => module.runs?.[step.id])?.id || \"\";", INDEX_HTML)
        self.assertIn("currentStepId || firstRunStepId", INDEX_HTML)

    def test_computation_stage_is_done_only_after_steps_complete(self) -> None:
        self.assertIn("done: computationDone", INDEX_HTML)
        self.assertNotIn("done: computationDone || flags.computationRefined", INDEX_HTML)

    def test_workspace_reuses_subpage_renderers_via_render_root(self) -> None:
        # 子页面渲染进入工作台容器，并在工作台内隐藏自身页头。
        self.assertIn("getRenderRoot", INDEX_HTML)
        self.assertIn("renderProjectMaintenanceStack", INDEX_HTML)
        self.assertIn("renderProjectDeliveryStack", INDEX_HTML)
        self.assertIn("state.inWorkspace", INDEX_HTML)

    def test_workspace_legacy_routes_redirect(self) -> None:
        # 旧 page=detail/requirements/execution 统一重定向到工作台对应 Tab。
        self.assertIn('detail: { page: "workspace", tab: "overview" }', INDEX_HTML)
        self.assertIn("replaceUrlWithWorkspace", INDEX_HTML)
        self.assertIn("legacyRoutePage", INDEX_HTML)

    def test_create_and_list_enter_workspace(self) -> None:
        # 新建项目落到工作台方案设计标签；项目列表先预览，再从预览进入工作台。
        self.assertIn('navigateTo("workspace", data.project.id, { tab: "plan" })', INDEX_HTML)
        self.assertIn("openProjectPreview(row.dataset.id)", INDEX_HTML)
        self.assertIn('navigateTo("workspace", project.id, { tab: "overview" })', INDEX_HTML)

    def test_deleting_active_workspace_project_redirects_to_valid_destination(self) -> None:
        self.assertIn("function syncWorkspaceAfterProjectDeletion(deletedIds)", INDEX_HTML)
        self.assertIn("syncWorkspaceAfterProjectDeletion(deletedIds)", INDEX_HTML)
        self.assertIn('navigateTo("workspace", state.projectDetail.id, { tab: "overview" })', INDEX_HTML)
        self.assertIn('navigateTo("projects")', INDEX_HTML)

    def test_requirement_upload_carries_project_id(self) -> None:
        self.assertIn("projectId: state.inWorkspace", INDEX_HTML)


if __name__ == "__main__":
    unittest.main()
