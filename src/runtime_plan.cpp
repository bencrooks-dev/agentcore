#include "runtime_plan.h"

#include <stdexcept>
#include <utility>

namespace marrow {

void RuntimePlan::set_meta(std::string version, std::string runtime_plan_id,
                           std::string graph_id, std::string name,
                           std::string entrypoint) {
    version_ = std::move(version);
    runtime_plan_id_ = std::move(runtime_plan_id);
    graph_id_ = std::move(graph_id);
    name_ = std::move(name);
    entrypoint_ = std::move(entrypoint);
}

void RuntimePlan::add_node(RuntimeNode node) {
    if (node_index_.count(node.id)) {
        throw std::runtime_error("duplicate node id: " + node.id);
    }
    node_index_.emplace(node.id, nodes_.size());
    nodes_.push_back(std::move(node));
}

void RuntimePlan::add_edge(RuntimeEdge edge) {
    edges_.push_back(std::move(edge));
}

void RuntimePlan::add_tool_binding(ToolBinding binding) {
    const std::string key = binding.name;
    tools_[key] = std::move(binding);
}

void RuntimePlan::add_provider_binding(ProviderBinding binding) {
    const std::string key = binding.id;
    providers_[key] = std::move(binding);
}

bool RuntimePlan::has_node(const std::string& id) const {
    return node_index_.count(id) > 0;
}

const RuntimeNode& RuntimePlan::node(const std::string& id) const {
    auto it = node_index_.find(id);
    if (it == node_index_.end()) {
        throw std::out_of_range("unknown node: " + id);
    }
    return nodes_[it->second];
}

bool RuntimePlan::has_provider(const std::string& id) const {
    return providers_.count(id) > 0;
}

const ProviderBinding& RuntimePlan::provider(const std::string& id) const {
    auto it = providers_.find(id);
    if (it == providers_.end()) {
        throw std::out_of_range("unknown provider: " + id);
    }
    return it->second;
}

bool RuntimePlan::has_tool(const std::string& name) const {
    return tools_.count(name) > 0;
}

const ToolBinding& RuntimePlan::tool(const std::string& name) const {
    auto it = tools_.find(name);
    if (it == tools_.end()) {
        throw std::out_of_range("unknown tool: " + name);
    }
    return it->second;
}

std::vector<std::string> RuntimePlan::node_ids() const {
    std::vector<std::string> out;
    out.reserve(nodes_.size());
    for (const auto& n : nodes_) out.push_back(n.id);
    return out;
}

std::vector<std::string> RuntimePlan::provider_ids() const {
    std::vector<std::string> out;
    out.reserve(providers_.size());
    for (const auto& [id, _] : providers_) out.push_back(id);
    return out;
}

std::vector<std::string> RuntimePlan::tool_names() const {
    std::vector<std::string> out;
    out.reserve(tools_.size());
    for (const auto& [name, _] : tools_) out.push_back(name);
    return out;
}

}  // namespace marrow
