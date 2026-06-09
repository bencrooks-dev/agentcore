// marrow — native representation of a compiled RuntimePlan.
//
// A RuntimePlan is produced by the (Python) Marrow compiler and lowered onto
// this C++ type so the native runtime can hold and inspect it. The core does
// NOT parse JSON: the Python side validates the plan and constructs this object
// across the pybind boundary (see marrow.compiler.load_runtime_plan). "Loading"
// a plan therefore means constructing and inspecting it here in C++.
#pragma once

#include <cstddef>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace marrow {

struct RuntimeNode {
    std::string id;
    std::string name;
    std::string provider;        // provider id, resolved in provider_bindings
    std::string system_prompt;
    std::vector<std::string> tools;
};

struct RuntimeEdge {
    std::string from;
    std::string to;
    std::string condition_type;  // "always" | "contains"
    std::string condition_value; // payload for "contains"; empty otherwise
};

struct ToolBinding {
    std::string name;
    int timeout_ms = 0;
    bool side_effects = false;
    bool requires_approval = false;
    std::string input_schema_json;   // opaque JSON Schema, stored verbatim
    std::string output_schema_json;
};

struct ProviderBinding {
    std::string id;
    std::string type;
    std::string model;
    std::optional<std::string> config_ref;
};

// A held, inspectable plan. Built incrementally; not thread-safe (a plan is
// constructed once on one thread, then read).
class RuntimePlan {
public:
    RuntimePlan() = default;

    // Parse a RuntimePlan from its JSON form — a real native load (the core's
    // own dependency-free JSON parser, no data marshalled field-by-field from
    // Python).
    static RuntimePlan from_json(const std::string& text);

    void set_meta(std::string version, std::string runtime_plan_id,
                  std::string graph_id, std::string name, std::string entrypoint);
    void add_node(RuntimeNode node);
    void add_edge(RuntimeEdge edge);
    void add_tool_binding(ToolBinding binding);
    void add_provider_binding(ProviderBinding binding);

    const std::string& version() const noexcept { return version_; }
    const std::string& runtime_plan_id() const noexcept { return runtime_plan_id_; }
    const std::string& graph_id() const noexcept { return graph_id_; }
    const std::string& name() const noexcept { return name_; }
    const std::string& entrypoint() const noexcept { return entrypoint_; }

    std::size_t node_count() const noexcept { return nodes_.size(); }
    std::size_t edge_count() const noexcept { return edges_.size(); }
    const std::vector<RuntimeNode>& nodes() const noexcept { return nodes_; }
    const std::vector<RuntimeEdge>& edges() const noexcept { return edges_; }

    // Lookups return by value (the structs are small) so a held result can
    // never dangle if the plan is mutated afterwards. Throw if absent.
    bool has_node(const std::string& id) const;
    RuntimeNode node(const std::string& id) const;
    bool has_provider(const std::string& id) const;
    ProviderBinding provider(const std::string& id) const;
    bool has_tool(const std::string& name) const;
    ToolBinding tool(const std::string& name) const;

    // Ids are returned in a deterministic order (insertion order for nodes,
    // sorted for the map-backed providers/tools).
    std::vector<std::string> node_ids() const;
    std::vector<std::string> provider_ids() const;
    std::vector<std::string> tool_names() const;

private:
    std::string version_;
    std::string runtime_plan_id_;
    std::string graph_id_;
    std::string name_;
    std::string entrypoint_;
    std::vector<RuntimeNode> nodes_;
    std::vector<RuntimeEdge> edges_;
    std::unordered_map<std::string, std::size_t> node_index_;
    std::unordered_map<std::string, ProviderBinding> providers_;
    std::unordered_map<std::string, ToolBinding> tools_;
};

}  // namespace marrow
