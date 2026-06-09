// marrow — a small, dependency-free JSON parser/serializer.
//
// Just enough JSON for the runtime to load a RuntimePlan and serialize an
// ExecutionTrace without linking a third-party library (keeping the core's
// dependency footprint near-zero, per ARI-SPEC §10.2). It parses standard JSON
// (objects, arrays, strings with escapes incl. \uXXXX + surrogate pairs,
// numbers, true/false/null) and serializes compactly. Object member order is
// preserved.
#pragma once

#include <cstdint>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace marrow {
namespace json {

class Value;
using Array = std::vector<Value>;
using Member = std::pair<std::string, Value>;
using Object = std::vector<Member>;

class Value {
public:
    enum class Type { Null, Bool, Int, Double, String, Array, Object };

    Value() : type_(Type::Null) {}

    static Value null() { return Value(); }
    static Value boolean(bool b) { Value v; v.type_ = Type::Bool; v.bool_ = b; return v; }
    static Value integer(long long i) { Value v; v.type_ = Type::Int; v.int_ = i; return v; }
    static Value number(double d) { Value v; v.type_ = Type::Double; v.dbl_ = d; return v; }
    static Value string(std::string s) { Value v; v.type_ = Type::String; v.str_ = std::move(s); return v; }
    static Value array() { Value v; v.type_ = Type::Array; return v; }
    static Value object() { Value v; v.type_ = Type::Object; return v; }

    Type type() const noexcept { return type_; }
    bool is_object() const noexcept { return type_ == Type::Object; }
    bool is_array() const noexcept { return type_ == Type::Array; }
    bool is_string() const noexcept { return type_ == Type::String; }
    bool is_number() const noexcept { return type_ == Type::Int || type_ == Type::Double; }

    const std::string& as_string() const { return str_; }
    bool as_bool() const noexcept { return bool_; }
    long long as_int() const noexcept { return type_ == Type::Double ? static_cast<long long>(dbl_) : int_; }
    double as_double() const noexcept { return type_ == Type::Int ? static_cast<double>(int_) : dbl_; }

    // --- object ---
    void set(std::string key, Value value) { obj_.emplace_back(std::move(key), std::move(value)); }
    const Object& members() const noexcept { return obj_; }
    const Value* find(const std::string& key) const {
        for (const auto& m : obj_) if (m.first == key) return &m.second;
        return nullptr;
    }
    std::string get_string(const std::string& key, const std::string& fallback = "") const {
        const Value* v = find(key);
        return (v && v->is_string()) ? v->as_string() : fallback;
    }
    long long get_int(const std::string& key, long long fallback = 0) const {
        const Value* v = find(key);
        return (v && v->is_number()) ? v->as_int() : fallback;
    }
    bool get_bool(const std::string& key, bool fallback = false) const {
        const Value* v = find(key);
        return (v && v->type_ == Type::Bool) ? v->bool_ : fallback;
    }

    // --- array ---
    void push_back(Value value) { arr_.push_back(std::move(value)); }
    const Array& items() const noexcept { return arr_; }

private:
    Type type_;
    bool bool_ = false;
    long long int_ = 0;
    double dbl_ = 0.0;
    std::string str_;
    Array arr_;
    Object obj_;
};

// ---------- parsing ----------

namespace detail {

inline void skip_ws(const char*& s, const char* end) {
    while (s < end && (*s == ' ' || *s == '\t' || *s == '\n' || *s == '\r')) ++s;
}

inline void append_utf8(std::string& out, unsigned int cp) {
    if (cp < 0x80) {
        out += static_cast<char>(cp);
    } else if (cp < 0x800) {
        out += static_cast<char>(0xC0 | (cp >> 6));
        out += static_cast<char>(0x80 | (cp & 0x3F));
    } else if (cp < 0x10000) {
        out += static_cast<char>(0xE0 | (cp >> 12));
        out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
        out += static_cast<char>(0x80 | (cp & 0x3F));
    } else {
        out += static_cast<char>(0xF0 | (cp >> 18));
        out += static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
        out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
        out += static_cast<char>(0x80 | (cp & 0x3F));
    }
}

inline unsigned int parse_hex4(const char*& s, const char* end) {
    if (s + 4 > end) throw std::runtime_error("json: truncated \\u escape");
    unsigned int code = 0;
    for (int i = 0; i < 4; ++i) {
        char c = *s++;
        code <<= 4;
        if (c >= '0' && c <= '9') code |= static_cast<unsigned int>(c - '0');
        else if (c >= 'a' && c <= 'f') code |= static_cast<unsigned int>(c - 'a' + 10);
        else if (c >= 'A' && c <= 'F') code |= static_cast<unsigned int>(c - 'A' + 10);
        else throw std::runtime_error("json: bad hex in \\u escape");
    }
    return code;
}

inline std::string parse_string(const char*& s, const char* end) {
    ++s;  // opening quote
    std::string out;
    while (s < end && *s != '"') {
        char c = *s++;
        if (c != '\\') { out += c; continue; }
        if (s >= end) throw std::runtime_error("json: truncated escape");
        char e = *s++;
        switch (e) {
            case '"': out += '"'; break;
            case '\\': out += '\\'; break;
            case '/': out += '/'; break;
            case 'b': out += '\b'; break;
            case 'f': out += '\f'; break;
            case 'n': out += '\n'; break;
            case 'r': out += '\r'; break;
            case 't': out += '\t'; break;
            case 'u': {
                unsigned int cp = parse_hex4(s, end);
                if (cp >= 0xD800 && cp <= 0xDBFF) {  // high surrogate
                    if (s + 2 <= end && s[0] == '\\' && s[1] == 'u') {
                        s += 2;
                        unsigned int lo = parse_hex4(s, end);
                        cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                    }
                }
                append_utf8(out, cp);
                break;
            }
            default: throw std::runtime_error("json: invalid escape");
        }
    }
    if (s >= end) throw std::runtime_error("json: unterminated string");
    ++s;  // closing quote
    return out;
}

inline Value parse_value(const char*& s, const char* end);

inline Value parse_number(const char*& s, const char* end) {
    const char* start = s;
    bool is_int = true;
    if (s < end && *s == '-') ++s;
    while (s < end && *s >= '0' && *s <= '9') ++s;
    if (s < end && *s == '.') { is_int = false; ++s; while (s < end && *s >= '0' && *s <= '9') ++s; }
    if (s < end && (*s == 'e' || *s == 'E')) {
        is_int = false; ++s;
        if (s < end && (*s == '+' || *s == '-')) ++s;
        while (s < end && *s >= '0' && *s <= '9') ++s;
    }
    std::string num(start, s);
    if (num.empty() || num == "-") throw std::runtime_error("json: invalid number");
    return is_int ? Value::integer(std::stoll(num)) : Value::number(std::stod(num));
}

inline void expect_literal(const char*& s, const char* end, const char* lit) {
    for (const char* p = lit; *p; ++p) {
        if (s >= end || *s != *p) throw std::runtime_error("json: invalid literal");
        ++s;
    }
}

inline Value parse_object(const char*& s, const char* end) {
    Value obj = Value::object();
    ++s;  // '{'
    skip_ws(s, end);
    if (s < end && *s == '}') { ++s; return obj; }
    while (true) {
        skip_ws(s, end);
        if (s >= end || *s != '"') throw std::runtime_error("json: expected object key");
        std::string key = parse_string(s, end);
        skip_ws(s, end);
        if (s >= end || *s != ':') throw std::runtime_error("json: expected ':'");
        ++s;
        obj.set(std::move(key), parse_value(s, end));
        skip_ws(s, end);
        if (s >= end) throw std::runtime_error("json: unterminated object");
        if (*s == ',') { ++s; continue; }
        if (*s == '}') { ++s; break; }
        throw std::runtime_error("json: expected ',' or '}'");
    }
    return obj;
}

inline Value parse_array(const char*& s, const char* end) {
    Value arr = Value::array();
    ++s;  // '['
    skip_ws(s, end);
    if (s < end && *s == ']') { ++s; return arr; }
    while (true) {
        arr.push_back(parse_value(s, end));
        skip_ws(s, end);
        if (s >= end) throw std::runtime_error("json: unterminated array");
        if (*s == ',') { ++s; continue; }
        if (*s == ']') { ++s; break; }
        throw std::runtime_error("json: expected ',' or ']'");
    }
    return arr;
}

inline Value parse_value(const char*& s, const char* end) {
    skip_ws(s, end);
    if (s >= end) throw std::runtime_error("json: unexpected end of input");
    char c = *s;
    if (c == '"') return Value::string(parse_string(s, end));
    if (c == '{') return parse_object(s, end);
    if (c == '[') return parse_array(s, end);
    if (c == 't') { expect_literal(s, end, "true"); return Value::boolean(true); }
    if (c == 'f') { expect_literal(s, end, "false"); return Value::boolean(false); }
    if (c == 'n') { expect_literal(s, end, "null"); return Value::null(); }
    return parse_number(s, end);
}

}  // namespace detail

inline Value parse(const std::string& text) {
    const char* s = text.data();
    const char* end = s + text.size();
    Value v = detail::parse_value(s, end);
    detail::skip_ws(s, end);
    if (s != end) throw std::runtime_error("json: trailing content after value");
    return v;
}

// ---------- serializing ----------

namespace detail {

inline void dump_string(const std::string& s, std::string& out) {
    out += '"';
    for (char c : s) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (static_cast<unsigned char>(c) < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof(buf), "\\u%04x", static_cast<unsigned char>(c));
                    out += buf;
                } else {
                    out += c;
                }
        }
    }
    out += '"';
}

inline void dump_value(const Value& v, std::string& out) {
    switch (v.type()) {
        case Value::Type::Null: out += "null"; break;
        case Value::Type::Bool: out += v.as_bool() ? "true" : "false"; break;
        case Value::Type::Int: out += std::to_string(v.as_int()); break;
        case Value::Type::Double: {
            char buf[32];
            std::snprintf(buf, sizeof(buf), "%.17g", v.as_double());
            out += buf;
            break;
        }
        case Value::Type::String: dump_string(v.as_string(), out); break;
        case Value::Type::Array: {
            out += '[';
            bool first = true;
            for (const auto& item : v.items()) {
                if (!first) out += ',';
                first = false;
                dump_value(item, out);
            }
            out += ']';
            break;
        }
        case Value::Type::Object: {
            out += '{';
            bool first = true;
            for (const auto& m : v.members()) {
                if (!first) out += ',';
                first = false;
                dump_string(m.first, out);
                out += ':';
                dump_value(m.second, out);
            }
            out += '}';
            break;
        }
    }
}

}  // namespace detail

inline std::string dump(const Value& v) {
    std::string out;
    detail::dump_value(v, out);
    return out;
}

}  // namespace json
}  // namespace marrow
