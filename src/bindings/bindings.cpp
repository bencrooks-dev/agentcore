// Pybind11 bindings for marrow.
//
// Provider is exposed as a base class with a trampoline (PyProvider)
// so Python can subclass it and have C++ call back into Python.
//
// Tools registered from Python are wrapped into a std::function<string(string)>;
// the captured py::function is held until the registry is cleared / engine
// destructs (both happen with the GIL held).

#include "engine.hpp"
#include "execution_trace.h"
#include "runtime_plan.h"

#include <pybind11/functional.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;
using namespace marrow;

// Trampoline so Python can subclass Provider.
class PyProvider : public Provider {
public:
    using Provider::Provider;
    std::string name() const override {
        PYBIND11_OVERRIDE_PURE(std::string, Provider, name);
    }
    GenerationResponse generate(const GenerationRequest& req) override {
        PYBIND11_OVERRIDE_PURE(GenerationResponse, Provider, generate, req);
    }
    void generate_stream(const GenerationRequest& req,
                         StreamCallback on_chunk) override {
        PYBIND11_OVERRIDE(void, Provider, generate_stream, req, on_chunk);
    }
};

PYBIND11_MODULE(_marrow, m) {
    m.doc() = "marrow — C++ engine for lightweight agent orchestration";

    py::enum_<Role>(m, "Role")
        .value("System",    Role::System)
        .value("User",      Role::User)
        .value("Assistant", Role::Assistant)
        .value("Tool",      Role::Tool);

    py::class_<Message>(m, "Message")
        .def(py::init<>())
        .def_static("make", &Message::make,
                    py::arg("role"), py::arg("content"), py::arg("name") = "")
        .def_readwrite("role",         &Message::role)
        // Validate on assignment so the kMaxContentBytes ceiling cannot be
        // bypassed by setting `.content` directly after construction (the
        // make() factory enforces the same bound on the construction path).
        .def_property("content",
                      [](const Message& m) { return m.content; },
                      [](Message& m, std::string v) {
                          if (v.size() > Message::kMaxContentBytes) {
                              throw std::runtime_error(
                                  "Message content exceeds " +
                                  std::to_string(Message::kMaxContentBytes) +
                                  " bytes");
                          }
                          m.content = std::move(v);
                      })
        .def_readwrite("name",         &Message::name)
        .def_readwrite("timestamp_ms", &Message::timestamp_ms)
        .def_readwrite("metadata",     &Message::metadata)
        .def("__repr__", [](const Message& m) {
            return "<Message role=" + std::to_string(static_cast<int>(m.role)) +
                   " name='" + m.name + "' content='" +
                   (m.content.size() > 60 ? m.content.substr(0, 57) + "..." : m.content) +
                   "'>";
        });

    py::class_<CancelToken, std::shared_ptr<CancelToken>>(m, "CancelToken")
        .def(py::init<>())
        .def("cancel",    &CancelToken::cancel)
        .def("reset",     &CancelToken::reset)
        .def("cancelled", &CancelToken::cancelled);

    py::enum_<OverflowPolicy>(m, "OverflowPolicy")
        .value("Reject",     OverflowPolicy::Reject)
        .value("DropOldest", OverflowPolicy::DropOldest)
        .value("DropNewest", OverflowPolicy::DropNewest);

    py::class_<GenerationRequest>(m, "GenerationRequest")
        .def(py::init<>())
        .def_readwrite("model",        &GenerationRequest::model)
        .def_readwrite("messages",     &GenerationRequest::messages)
        .def_readwrite("temperature",  &GenerationRequest::temperature)
        .def_readwrite("max_tokens",   &GenerationRequest::max_tokens)
        .def_readwrite("timeout_ms",   &GenerationRequest::timeout_ms)
        .def_readwrite("cancel_token", &GenerationRequest::cancel_token);

    py::class_<GenerationResponse>(m, "GenerationResponse")
        .def(py::init<>())
        .def_readwrite("content",           &GenerationResponse::content)
        .def_readwrite("prompt_tokens",     &GenerationResponse::prompt_tokens)
        .def_readwrite("completion_tokens", &GenerationResponse::completion_tokens);

    // call_guard releases the GIL during generate/generate_stream so other
    // Python threads can make progress. The PYBIND11_OVERRIDE_* macros in
    // the PyProvider trampoline re-acquire the GIL when calling back into
    // Python — this is required for correctness when a Python subclass
    // (OpenAIProvider, AnthropicProvider, etc.) is invoked from a worker
    // thread via AsyncRuntime.
    py::class_<Provider, PyProvider, std::shared_ptr<Provider>>(m, "Provider")
        .def(py::init<>())
        .def("name",            &Provider::name)
        .def("generate",        &Provider::generate,
             py::call_guard<py::gil_scoped_release>())
        .def("generate_stream", &Provider::generate_stream,
             py::call_guard<py::gil_scoped_release>(),
             py::arg("req"), py::arg("on_chunk"));

    py::class_<MockProvider, Provider, std::shared_ptr<MockProvider>>(m, "MockProvider")
        .def(py::init<std::string>(), py::arg("name") = "mock")
        .def("name",            &MockProvider::name)
        .def("generate",        &MockProvider::generate,
             py::call_guard<py::gil_scoped_release>())
        .def("generate_stream", &MockProvider::generate_stream,
             py::call_guard<py::gil_scoped_release>(),
             py::arg("req"), py::arg("on_chunk"));

    py::class_<AgentState, std::shared_ptr<AgentState>>(m, "AgentState")
        .def_property_readonly("id", &AgentState::id)
        .def("append",            &AgentState::append)
        .def("history",           &AgentState::history)
        .def("size",              &AgentState::size)
        .def("clear",             &AgentState::clear)
        .def("set_system_prompt", &AgentState::set_system_prompt)
        .def("system_prompt",     &AgentState::system_prompt)
        .def("trimmed",           &AgentState::trimmed, py::arg("max_messages"));

    py::class_<MemoryCache>(m, "MemoryCache")
        .def(py::init<std::size_t>(), py::arg("capacity") = 1024)
        .def("put",      &MemoryCache::put)
        .def("get",      &MemoryCache::get)
        .def("contains", &MemoryCache::contains)
        .def("erase",    &MemoryCache::erase)
        .def("clear",    &MemoryCache::clear)
        .def("size",     &MemoryCache::size);

    py::class_<RoutedMessage>(m, "RoutedMessage")
        .def_readwrite("from_",   &RoutedMessage::from)
        .def_readwrite("to",      &RoutedMessage::to)
        .def_readwrite("message", &RoutedMessage::message);

    py::class_<AgentRouter>(m, "AgentRouter")
        .def("register_agent",   &AgentRouter::register_agent)
        .def("unregister_agent", &AgentRouter::unregister_agent)
        .def("has_agent",        &AgentRouter::has_agent)
        .def("agents",           &AgentRouter::agents)
        .def("set_inbox_limit",  &AgentRouter::set_inbox_limit,
             py::arg("agent_id"), py::arg("max_size"),
             py::arg("policy") = OverflowPolicy::Reject)
        .def("inbox_size",       &AgentRouter::inbox_size)
        .def("send",             &AgentRouter::send,
             py::arg("from"), py::arg("to"), py::arg("msg"))
        .def("drain",            &AgentRouter::drain)
        .def("handoff",          &AgentRouter::handoff,
             py::arg("from"), py::arg("to"), py::arg("seed") = std::nullopt)
        .def("active",           &AgentRouter::active)
        .def("set_active",       &AgentRouter::set_active);

    py::class_<ToolRegistry>(m, "ToolRegistry")
        .def("has",         &ToolRegistry::has)
        .def("names",       &ToolRegistry::names)
        .def("description", &ToolRegistry::description)
        .def("schema",      &ToolRegistry::schema)
        .def("clear",       &ToolRegistry::clear)
        .def("register",
             [](ToolRegistry& self, std::string name, std::string description,
                std::string schema, py::function fn) {
                 // Hold the py::function in a shared_ptr whose deleter
                 // acquires the GIL. This makes the captured function
                 // safe to destruct from any thread (including a worker
                 // thread that doesn't hold the GIL, or interpreter
                 // shutdown). Copying the lambda copies the shared_ptr
                 // (atomic refcount, no GIL required), not the py::function.
                 auto fn_holder = std::shared_ptr<py::function>(
                     new py::function(std::move(fn)),
                     [](py::function* p) {
                         py::gil_scoped_acquire gil;
                         delete p;
                     });
                 ToolFn wrapped =
                     [fn_holder = std::move(fn_holder)](const std::string& args) -> std::string {
                         py::gil_scoped_acquire gil;
                         py::object result = (*fn_holder)(args);
                         return py::cast<std::string>(result);
                     };
                 self.register_tool(ToolSpec{
                     std::move(name), std::move(description),
                     std::move(schema), std::move(wrapped)});
             },
             py::arg("name"), py::arg("description") = "",
             py::arg("schema") = "{}", py::arg("fn"))
        // NOTE: no gil_scoped_release here.
        // Tools registered from Python are stored as std::function objects
        // that capture a py::function by value. Copying the std::function
        // (which `invoke` does to release the registry lock before calling)
        // copies the captured py::function, which increments a PyObject
        // refcount — that operation requires the GIL. Tools run Python
        // bodies anyway, so releasing/re-acquiring would save nothing.
        .def("invoke", &ToolRegistry::invoke,
             py::arg("name"), py::arg("args_json"));

    // reference_internal returns by reference and keeps the Engine alive
    // for as long as the returned handle is alive — defends against
    // `r = engine.router; del engine; r.send(...)` use-after-free.
    py::class_<Engine>(m, "Engine")
        .def(py::init<>())
        .def("create_agent", &Engine::create_agent)
        .def("agent",        &Engine::agent)
        .def("shutdown",     &Engine::shutdown)
        .def("is_shutdown",  &Engine::is_shutdown)
        .def_property_readonly("router", &Engine::router,
                               py::return_value_policy::reference_internal)
        .def_property_readonly("cache",  &Engine::cache,
                               py::return_value_policy::reference_internal)
        .def_property_readonly("tools",  &Engine::tools,
                               py::return_value_policy::reference_internal);

    // ----- Compiler: native RuntimePlan + ExecutionTrace -----
    //
    // These hold the output of the (Python) Marrow compiler so the native
    // runtime can represent and inspect a plan, and record a trace. The core
    // links no JSON parser; the Python side constructs these across the binding
    // boundary (marrow.compiler.load_runtime_plan). Registered dependency-first
    // so member types resolve.

    py::class_<RuntimeNode>(m, "RuntimeNode")
        .def(py::init([](std::string id, std::string name, std::string provider,
                         std::string system_prompt, std::vector<std::string> tools) {
                 return RuntimeNode{std::move(id), std::move(name), std::move(provider),
                                    std::move(system_prompt), std::move(tools)};
             }),
             py::arg("id"), py::arg("name"), py::arg("provider"),
             py::arg("system_prompt") = "",
             py::arg("tools") = std::vector<std::string>{})
        .def_readwrite("id",            &RuntimeNode::id)
        .def_readwrite("name",          &RuntimeNode::name)
        .def_readwrite("provider",      &RuntimeNode::provider)
        .def_readwrite("system_prompt", &RuntimeNode::system_prompt)
        .def_readwrite("tools",         &RuntimeNode::tools);

    py::class_<RuntimeEdge>(m, "RuntimeEdge")
        .def(py::init([](std::string from, std::string to,
                         std::string condition_type, std::string condition_value) {
                 return RuntimeEdge{std::move(from), std::move(to),
                                    std::move(condition_type), std::move(condition_value)};
             }),
             py::arg("from"), py::arg("to"),
             py::arg("condition_type") = "always", py::arg("condition_value") = "")
        .def_readwrite("from_",           &RuntimeEdge::from)
        .def_readwrite("to",              &RuntimeEdge::to)
        .def_readwrite("condition_type",  &RuntimeEdge::condition_type)
        .def_readwrite("condition_value", &RuntimeEdge::condition_value);

    py::class_<ToolBinding>(m, "ToolBinding")
        .def(py::init([](std::string name, int timeout_ms, bool side_effects,
                         bool requires_approval, std::string input_schema_json,
                         std::string output_schema_json) {
                 return ToolBinding{std::move(name), timeout_ms, side_effects,
                                    requires_approval, std::move(input_schema_json),
                                    std::move(output_schema_json)};
             }),
             py::arg("name"), py::arg("timeout_ms") = 0,
             py::arg("side_effects") = false, py::arg("requires_approval") = false,
             py::arg("input_schema_json") = "{}", py::arg("output_schema_json") = "{}")
        .def_readwrite("name",               &ToolBinding::name)
        .def_readwrite("timeout_ms",         &ToolBinding::timeout_ms)
        .def_readwrite("side_effects",       &ToolBinding::side_effects)
        .def_readwrite("requires_approval",  &ToolBinding::requires_approval)
        .def_readwrite("input_schema_json",  &ToolBinding::input_schema_json)
        .def_readwrite("output_schema_json", &ToolBinding::output_schema_json);

    py::class_<ProviderBinding>(m, "ProviderBinding")
        .def(py::init([](std::string id, std::string type, std::string model,
                         std::optional<std::string> config_ref) {
                 return ProviderBinding{std::move(id), std::move(type),
                                        std::move(model), std::move(config_ref)};
             }),
             py::arg("id"), py::arg("type"), py::arg("model"),
             py::arg("config_ref") = std::nullopt)
        .def_readwrite("id",         &ProviderBinding::id)
        .def_readwrite("type",       &ProviderBinding::type)
        .def_readwrite("model",      &ProviderBinding::model)
        .def_readwrite("config_ref", &ProviderBinding::config_ref);

    py::class_<RuntimePlan>(m, "RuntimePlan")
        .def(py::init<>())
        .def("set_meta", &RuntimePlan::set_meta,
             py::arg("version"), py::arg("runtime_plan_id"), py::arg("graph_id"),
             py::arg("name"), py::arg("entrypoint"))
        .def("add_node",             &RuntimePlan::add_node)
        .def("add_edge",             &RuntimePlan::add_edge)
        .def("add_tool_binding",     &RuntimePlan::add_tool_binding)
        .def("add_provider_binding", &RuntimePlan::add_provider_binding)
        .def_property_readonly("version",         &RuntimePlan::version)
        .def_property_readonly("runtime_plan_id", &RuntimePlan::runtime_plan_id)
        .def_property_readonly("graph_id",        &RuntimePlan::graph_id)
        .def_property_readonly("name",            &RuntimePlan::name)
        .def_property_readonly("entrypoint",      &RuntimePlan::entrypoint)
        .def("node_count", &RuntimePlan::node_count)
        .def("edge_count", &RuntimePlan::edge_count)
        .def("nodes",      &RuntimePlan::nodes)
        .def("edges",      &RuntimePlan::edges)
        .def("has_node",   &RuntimePlan::has_node)
        .def("node",       &RuntimePlan::node, py::return_value_policy::reference_internal)
        .def("has_provider", &RuntimePlan::has_provider)
        .def("provider",   &RuntimePlan::provider, py::return_value_policy::reference_internal)
        .def("has_tool",   &RuntimePlan::has_tool)
        .def("tool",       &RuntimePlan::tool, py::return_value_policy::reference_internal)
        .def("node_ids",     &RuntimePlan::node_ids)
        .def("provider_ids", &RuntimePlan::provider_ids)
        .def("tool_names",   &RuntimePlan::tool_names);

    py::class_<TraceEvent>(m, "TraceEvent")
        .def_readwrite("type",       &TraceEvent::type)
        .def_readwrite("attributes", &TraceEvent::attributes);

    py::class_<ToolCall>(m, "ToolCall")
        .def(py::init([](std::string agent, std::string tool, std::string args_json,
                         std::string result_json, bool ok) {
                 return ToolCall{std::move(agent), std::move(tool), std::move(args_json),
                                 std::move(result_json), ok};
             }),
             py::arg("agent"), py::arg("tool"), py::arg("args_json") = "",
             py::arg("result_json") = "", py::arg("ok") = true)
        .def_readwrite("agent",       &ToolCall::agent)
        .def_readwrite("tool",        &ToolCall::tool)
        .def_readwrite("args_json",   &ToolCall::args_json)
        .def_readwrite("result_json", &ToolCall::result_json)
        .def_readwrite("ok",          &ToolCall::ok);

    py::class_<ProviderCall>(m, "ProviderCall")
        .def(py::init([](std::string agent, std::string provider, std::string model,
                         int prompt_tokens, int completion_tokens) {
                 return ProviderCall{std::move(agent), std::move(provider),
                                     std::move(model), prompt_tokens, completion_tokens};
             }),
             py::arg("agent"), py::arg("provider"), py::arg("model"),
             py::arg("prompt_tokens") = 0, py::arg("completion_tokens") = 0)
        .def_readwrite("agent",             &ProviderCall::agent)
        .def_readwrite("provider",          &ProviderCall::provider)
        .def_readwrite("model",             &ProviderCall::model)
        .def_readwrite("prompt_tokens",     &ProviderCall::prompt_tokens)
        .def_readwrite("completion_tokens", &ProviderCall::completion_tokens);

    py::class_<TraceError>(m, "TraceError")
        .def(py::init([](std::string agent, std::string kind, std::string message) {
                 return TraceError{std::move(agent), std::move(kind), std::move(message)};
             }),
             py::arg("agent") = "", py::arg("kind") = "", py::arg("message") = "")
        .def_readwrite("agent",   &TraceError::agent)
        .def_readwrite("kind",    &TraceError::kind)
        .def_readwrite("message", &TraceError::message);

    py::class_<ExecutionTrace>(m, "ExecutionTrace")
        .def(py::init<>())
        .def(py::init<std::string, std::string>(),
             py::arg("trace_id"), py::arg("runtime_plan_id"))
        .def("set_input",        &ExecutionTrace::set_input)
        .def("set_started_at",   &ExecutionTrace::set_started_at)
        .def("set_completed_at", &ExecutionTrace::set_completed_at)
        .def("set_final_status", &ExecutionTrace::set_final_status)
        .def("add_event", &ExecutionTrace::add_event, py::arg("type"),
             py::arg("attributes") = std::vector<std::pair<std::string, std::string>>{})
        .def("add_tool_call",     &ExecutionTrace::add_tool_call)
        .def("add_provider_call", &ExecutionTrace::add_provider_call)
        .def("add_error",         &ExecutionTrace::add_error)
        .def_property_readonly("trace_id",        &ExecutionTrace::trace_id)
        .def_property_readonly("runtime_plan_id", &ExecutionTrace::runtime_plan_id)
        .def_property_readonly("has_input",       &ExecutionTrace::has_input)
        .def_property_readonly("input",           &ExecutionTrace::input)
        .def_property_readonly("started_at",      &ExecutionTrace::started_at)
        .def_property_readonly("completed_at",    &ExecutionTrace::completed_at)
        .def_property_readonly("final_status",    &ExecutionTrace::final_status)
        .def("events",         &ExecutionTrace::events)
        .def("tool_calls",     &ExecutionTrace::tool_calls)
        .def("provider_calls", &ExecutionTrace::provider_calls)
        .def("errors",         &ExecutionTrace::errors);
}
