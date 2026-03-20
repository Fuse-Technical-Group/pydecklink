cmake_minimum_required(VERSION 3.17)
project(test_capture_minimal LANGUAGES CXX)

find_package(ajantv2 REQUIRED)

add_executable(test_capture_minimal test_capture_minimal.cpp)
target_link_libraries(test_capture_minimal PRIVATE AJA::ajantv2)
