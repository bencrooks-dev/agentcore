// marrow — native ExecutionTrace.
//
// A portable record of one RuntimePlan execution. The executor (Python driver
// over the C++ engine) records events and calls into this native object as the
// run proceeds; Python then serialises it to ExecutionTrace JSON. Kept
// dependency-free: events carry a type plus an ordered list of string
// attributes rather than embedded JSON.
#pragma once

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace marrow {

struct TraceEvent {
    std::string type;
    std::vector<std::pair<std::string, std::string>> attributes;
};

struct ToolCall {
    std::string agent;
    std::string tool;
    std::string args_json;
    std::string result_json;
    bool ok = true;
};

struct ProviderCall {
    std::string agent;
    std::string provider;
    std::string model;
    int prompt_tokens = 0;
    int completion_tokens = 0;
};

struct TraceError {
    std::string agent;
    std::string kind;
    std::string message;
};

struct PolicyDecision {
    std::string action;
    std::string decision;        // "allow" | "deny" | "require_approval"
    bool allowed = true;
    bool approval_required = false;
    bool evidence_required = false;
};

struct BudgetUsage {
    int steps = 0;
    int prompt_tokens = 0;
    int completion_tokens = 0;
    double cost_usd = 0.0;
};

class ExecutionTrace {
public:
    ExecutionTrace() = default;
    ExecutionTrace(std::string trace_id, std::string runtime_plan_id);

    void set_input(std::string input);
    void set_started_at(std::int64_t ms) noexcept { started_at_ = ms; }
    void set_completed_at(std::int64_t ms) noexcept { completed_at_ = ms; }
    void set_final_status(std::string status) { final_status_ = std::move(status); }

    void add_event(std::string type,
                   std::vector<std::pair<std::string, std::string>> attributes = {});
    void add_tool_call(ToolCall call);
    void add_provider_call(ProviderCall call);
    void add_error(TraceError error);
    void add_policy_decision(PolicyDecision decision);
    void set_budget_usage(BudgetUsage usage);

    const std::string& trace_id() const noexcept { return trace_id_; }
    const std::string& runtime_plan_id() const noexcept { return runtime_plan_id_; }
    bool has_input() const noexcept { return has_input_; }
    const std::string& input() const noexcept { return input_; }
    std::int64_t started_at() const noexcept { return started_at_; }
    std::int64_t completed_at() const noexcept { return completed_at_; }
    const std::string& final_status() const noexcept { return final_status_; }

    const std::vector<TraceEvent>& events() const noexcept { return events_; }
    const std::vector<ToolCall>& tool_calls() const noexcept { return tool_calls_; }
    const std::vector<ProviderCall>& provider_calls() const noexcept { return provider_calls_; }
    const std::vector<TraceError>& errors() const noexcept { return errors_; }
    const std::vector<PolicyDecision>& policy_decisions() const noexcept { return policy_decisions_; }
    bool has_budget_usage() const noexcept { return has_budget_usage_; }
    const BudgetUsage& budget_usage() const noexcept { return budget_usage_; }

    // Serialize the trace to its JSON document form (the core's own JSON
    // writer — the trace is produced natively, not assembled in Python).
    std::string to_json() const;

private:
    std::string trace_id_;
    std::string runtime_plan_id_;
    bool has_input_ = false;
    std::string input_;
    std::int64_t started_at_ = 0;
    std::int64_t completed_at_ = 0;
    std::string final_status_ = "completed";
    std::vector<TraceEvent> events_;
    std::vector<ToolCall> tool_calls_;
    std::vector<ProviderCall> provider_calls_;
    std::vector<TraceError> errors_;
    std::vector<PolicyDecision> policy_decisions_;
    bool has_budget_usage_ = false;
    BudgetUsage budget_usage_{};
};

}  // namespace marrow
