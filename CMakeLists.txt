cmake_minimum_required(VERSION 3.18)
project(marrow LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

if(MSVC)
    add_compile_options(/W4 /permissive-)
else()
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(pybind11 CONFIG REQUIRED)

add_library(marrow_core STATIC
    src/core/engine.cpp
    src/runtime_plan.cpp
    src/execution_trace.cpp)
target_include_directories(marrow_core PUBLIC src/core src)
set_target_properties(marrow_core PROPERTIES POSITION_INDEPENDENT_CODE ON)

pybind11_add_module(_marrow src/bindings/bindings.cpp)
target_link_libraries(_marrow PRIVATE marrow_core)
target_include_directories(_marrow PRIVATE src/core src)

install(TARGETS _marrow LIBRARY DESTINATION marrow)
