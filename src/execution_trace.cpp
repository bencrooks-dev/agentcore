#include "execution_trace.h"

#include <utility>

#include "json.hpp"

namespace marrow {

std::string ExecutionTrace::to_json() const {
    using json::Value;
    Value root = Value::object();
    root.set("trace_id", Value::string(trace_id_));
    root.set("runtime_plan_id", Value::string(runtime_plan_id_));
    root.set("input", has_input_ ? Value::string(input_) : Value::null());
    root.set("started_at", Value::integer(started_at_));
    root.set("completed_at", Value::integer(completed_at_));

    Value events = Value::array();
    for (const auto& e : events_) {
        Value ev = Value::object();
        ev.set("type", Value::string(e.type));
        for (const auto& attr : e.attributes) ev.set(attr.first, Value::string(attr.second));
        events.push_back(std::move(ev));
    }
    root.set("events", std::move(events));

    Value tool_calls = Value::array();
    for (const auto& c : tool_calls_) {
        Value item = Value::object();
        item.set("agent", Value::string(c.agent));
        item.set("tool", Value::string(c.tool));
        item.set("args", Value::string(c.args_json));
        item.set("result", Value::string(c.result_json));
        item.set("ok", Value::boolean(c.ok));
        tool_calls.push_back(std::move(item));
    }
    root.set("tool_calls", std::move(tool_calls));

    Value provider_calls = Value::array();
    for (const auto& c : provider_calls_) {
        Value item = Value::object();
        item.set("agent", Value::string(c.agent));
        item.set("provider", Value::string(c.provider));
        item.set("model", Value::string(c.model));
        item.set("prompt_tokens", Value::integer(c.prompt_tokens));
        item.set("completion_tokens", Value::integer(c.completion_tokens));
        provider_calls.push_back(std::move(item));
    }
    root.set("provider_calls", std::move(provider_calls));

    Value decisions = Value::array();
    for (const auto& d : policy_decisions_) {
        Value item = Value::object();
        item.set("action", Value::string(d.action));
        item.set("decision", Value::string(d.decision));
        item.set("allowed", Value::boolean(d.allowed));
        item.set("approval_required", Value::boolean(d.approval_required));
        item.set("evidence_required", Value::boolean(d.evidence_required));
        decisions.push_back(std::move(item));
    }
    root.set("policy_decisions", std::move(decisions));

    Value errors = Value::array();
    for (const auto& e : errors_) {
        Value item = Value::object();
        item.set("agent", Value::string(e.agent));
        item.set("kind", Value::string(e.kind));
        item.set("message", Value::string(e.message));
        errors.push_back(std::move(item));
    }
    root.set("errors", std::move(errors));
    root.set("final_status", Value::string(final_status_));

    if (has_budget_usage_) {
        Value usage = Value::object();
        usage.set("steps", Value::integer(budget_usage_.steps));
        usage.set("prompt_tokens", Value::integer(budget_usage_.prompt_tokens));
        usage.set("completion_tokens", Value::integer(budget_usage_.completion_tokens));
        usage.set("total_tokens",
                  Value::integer(budget_usage_.prompt_tokens + budget_usage_.completion_tokens));
        usage.set("cost_usd", Value::number(budget_usage_.cost_usd));
        root.set("budget_usage", std::move(usage));
    }

    return json::dump(root);
}

ExecutionTrace::ExecutionTrace(std::string trace_id, std::string runtime_plan_id)
    : trace_id_(std::move(trace_id)),
      runtime_plan_id_(std::move(runtime_plan_id)) {}

void ExecutionTrace::set_input(std::string input) {
    input_ = std::move(input);
    has_input_ = true;
}

void ExecutionTrace::add_event(
    std::string type, std::vector<std::pair<std::string, std::string>> attributes) {
    events_.push_back(TraceEvent{std::move(type), std::move(attributes)});
}

void ExecutionTrace::add_tool_call(ToolCall call) {
    tool_calls_.push_back(std::move(call));
}

void ExecutionTrace::add_provider_call(ProviderCall call) {
    provider_calls_.push_back(std::move(call));
}

void ExecutionTrace::add_error(TraceError error) {
    errors_.push_back(std::move(error));
}

void ExecutionTrace::add_policy_decision(PolicyDecision decision) {
    policy_decisions_.push_back(std::move(decision));
}

void ExecutionTrace::set_budget_usage(BudgetUsage usage) {
    budget_usage_ = usage;
    has_budget_usage_ = true;
}

}  // namespace marrow
