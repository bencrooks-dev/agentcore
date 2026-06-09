#include "execution_trace.h"

#include <utility>

namespace marrow {

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

}  // namespace marrow
