# `marrow.compiler`

The compiler lowers a declaratively-defined agent graph into a portable,
executable plan and runs it. For a walkthrough see the
[Compiler concept page](../concepts/compiler.md).

::: marrow.compiler
    options:
      members:
        - AgentGraph
        - AgentNode
        - ToolSpec
        - ProviderSpec
        - PolicySpec
        - BudgetSpec
        - FailureSemantics
        - RollbackStep
        - Edge
        - compile_to_ari
        - ari_to_runtime_plan
        - compile_graph
        - compile_and_run
        - run_runtime_plan
        - load_runtime_plan
        - replay
        - traces_equivalent
        - normalize_trace
        - make_deployment_manifest
        - graph_id
        - runtime_plan_id
        - canonical_json
        - Approver
        - ProviderFactory
        - CompileError
