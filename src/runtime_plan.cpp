#include "runtime_plan.h"

#include <algorithm>
#include <stdexcept>
#include <utility>

#include "json.hpp"

namespace marrow {

RuntimePlan RuntimePlan::from_json(const std::string& text) {
    const json::Value root = json::parse(text);
    RuntimePlan plan;
    plan.set_meta(root.get_string("version"), root.get_string("runtime_plan_id"),
                  root.get_string("graph_id"), root.get_string("name"),
                  root.get_string("entrypoint"));

    if (const json::Value* nodes = root.find("nodes")) {
        for (const auto& n : nodes->items()) {
            RuntimeNode node;
            node.id = n.get_string("id");
            node.name = n.get_string("name");
            node.provider = n.get_string("provider");
            node.system_prompt = n.get_string("system_prompt");
            if (const json::Value* tools = n.find("tools")) {
                for (const auto& t : tools->items()) node.tools.push_back(t.as_string());
            }
            plan.add_node(std::move(node));
        }
    }
    if (const json::Value* edges = root.find("edges")) {
        for (const auto& e : edges->items()) {
            RuntimeEdge edge;
            edge.from = e.get_string("from");
            edge.to = e.get_string("to");
            if (const json::Value* cond = e.find("condition")) {
                edge.condition_type = cond->get_string("type");
                edge.condition_value = cond->get_string("value");
            }
            plan.add_edge(std::move(edge));
        }
    }
    if (const json::Value* bindings = root.find("tool_bindings")) {
        for (const auto& m : bindings->members()) {
            ToolBinding binding;
            binding.name = m.first;
            binding.timeout_ms = static_cast<int>(m.second.get_int("timeout_ms"));
            binding.side_effects = m.second.get_bool("side_effects");
            binding.requires_approval = m.second.get_bool("requires_approval");
            if (const json::Value* in = m.second.find("input_schema"))
                binding.input_schema_json = json::dump(*in);
            if (const json::Value* out = m.second.find("output_schema"))
                binding.output_schema_json = json::dump(*out);
            plan.add_tool_binding(std::move(binding));
        }
    }
    if (const json::Value* bindings = root.find("provider_bindings")) {
        for (const auto& m : bindings->members()) {
            ProviderBinding binding;
            binding.id = m.first;
            binding.type = m.second.get_string("type");
            binding.model = m.second.get_string("model");
            if (const json::Value* cr = m.second.find("config_ref")) {
                if (cr->is_string()) binding.config_ref = cr->as_string();
            }
            plan.add_provider_binding(std::move(binding));
        }
    }
    return plan;
}

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

RuntimeNode RuntimePlan::node(const std::string& id) const {
    auto it = node_index_.find(id);
    if (it == node_index_.end()) {
        throw std::out_of_range("unknown node: " + id);
    }
    return nodes_[it->second];
}

bool RuntimePlan::has_provider(const std::string& id) const {
    return providers_.count(id) > 0;
}

ProviderBinding RuntimePlan::provider(const std::string& id) const {
    auto it = providers_.find(id);
    if (it == providers_.end()) {
        throw std::out_of_range("unknown provider: " + id);
    }
    return it->second;
}

bool RuntimePlan::has_tool(const std::string& name) const {
    return tools_.count(name) > 0;
}

ToolBinding RuntimePlan::tool(const std::string& name) const {
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
    std::sort(out.begin(), out.end());  // map iteration order is unspecified
    return out;
}

std::vector<std::string> RuntimePlan::tool_names() const {
    std::vector<std::string> out;
    out.reserve(tools_.size());
    for (const auto& [name, _] : tools_) out.push_back(name);
    std::sort(out.begin(), out.end());  // map iteration order is unspecified
    return out;
}

}  // namespace marrow
