cmake_minimum_required(VERSION 3.26...3.31)
project(${SKBUILD_PROJECT_NAME} LANGUAGES CXX)

find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module Development.SABIModule)
find_package(nanobind CONFIG REQUIRED)

# Vendored DeckLink SDK headers (gitignored — not redistributed).
set(DECKLINK_SDK_DIR "${CMAKE_SOURCE_DIR}/vendor/Blackmagic DeckLink SDK 15.3/Linux/include")

set(_bindings_sources src/pydecklink_ext/bindings.cpp)

if(EXISTS "${DECKLINK_SDK_DIR}/DeckLinkAPIDispatch.cpp")
  list(APPEND _bindings_sources
    "${DECKLINK_SDK_DIR}/DeckLinkAPIDispatch.cpp"
    src/pydecklink_ext/bind_enums.cpp
    src/pydecklink_ext/bind_device.cpp
    src/pydecklink_ext/bind_format.cpp
    src/pydecklink_ext/bind_output.cpp
    src/pydecklink_ext/bind_input.cpp
  )
  set(HAVE_DECKLINK_SDK TRUE)
else()
  message(STATUS "DeckLink SDK not found — building without SDK dispatch")
  set(HAVE_DECKLINK_SDK FALSE)
endif()

nanobind_add_module(_bindings STABLE_ABI ${_bindings_sources})
target_include_directories(_bindings PRIVATE "${CMAKE_SOURCE_DIR}/src/pydecklink_ext")
if(HAVE_DECKLINK_SDK)
  target_include_directories(_bindings PRIVATE "${DECKLINK_SDK_DIR}")
  target_compile_definitions(_bindings PRIVATE HAVE_DECKLINK_SDK)
endif()
install(TARGETS _bindings LIBRARY DESTINATION pydecklink)

nanobind_add_stub(
  _bindings_stub
  INSTALL_TIME
  MODULE pydecklink._bindings
  OUTPUT pydecklink/_bindings.pyi
  PYTHON_PATH "."
  DEPENDS _bindings
)
