cmake_minimum_required(VERSION 3.26...3.31)
project(${SKBUILD_PROJECT_NAME} LANGUAGES CXX)

find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module Development.SABIModule)
find_package(nanobind CONFIG REQUIRED)
find_package(ajantv2 REQUIRED)

nanobind_add_module(_bindings STABLE_ABI
  src/bindings.cpp
  src/bind_enums.cpp
  src/bind_card.cpp
  src/bind_transfer.cpp
)
target_link_libraries(_bindings PRIVATE AJA::ajantv2)
install(TARGETS _bindings LIBRARY DESTINATION pyntv2)

nanobind_add_stub(
  _bindings_stub
  INSTALL_TIME
  MODULE pyntv2._bindings
  OUTPUT pyntv2/_bindings.pyi
  PYTHON_PATH "."
  DEPENDS _bindings
)
