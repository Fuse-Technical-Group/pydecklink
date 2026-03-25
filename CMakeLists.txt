cmake_minimum_required(VERSION 3.26...3.31)
project(${SKBUILD_PROJECT_NAME} LANGUAGES CXX)

find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module Development.SABIModule)
find_package(nanobind CONFIG REQUIRED)

# Vendored DeckLink SDK headers (gitignored — not redistributed).
set(DECKLINK_SDK_DIR "${CMAKE_SOURCE_DIR}/vendor/Blackmagic DeckLink SDK 15.3/Linux/include")

nanobind_add_module(_bindings STABLE_ABI
  src/pydecklink_ext/bindings.cpp
  "${DECKLINK_SDK_DIR}/DeckLinkAPIDispatch.cpp"
)
target_include_directories(_bindings PRIVATE "${DECKLINK_SDK_DIR}")
install(TARGETS _bindings LIBRARY DESTINATION pydecklink)

nanobind_add_stub(
  _bindings_stub
  INSTALL_TIME
  MODULE pydecklink._bindings
  OUTPUT pydecklink/_bindings.pyi
  PYTHON_PATH "."
  DEPENDS _bindings
)
