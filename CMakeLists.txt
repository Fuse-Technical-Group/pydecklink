cmake_minimum_required(VERSION 3.26...3.31)
project(${SKBUILD_PROJECT_NAME} LANGUAGES C CXX)

find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module Development.SABIModule)
find_package(nanobind CONFIG REQUIRED)

# Vendored DeckLink SDK headers (gitignored — not redistributed).
# DECKLINK_SDK_DIR may be set via cmake -D (scikit-build-core forwards it
# from pyproject.toml / env).  Resolve relative paths against the *source*
# directory so out-of-tree builds (sdist isolation) still find the headers
# when pointed at an absolute host path.
set(DECKLINK_SDK_DIR "${CMAKE_SOURCE_DIR}/vendor/Blackmagic DeckLink SDK 15.3/Linux/include" CACHE PATH "Path to DeckLink SDK include directory")
if(NOT IS_ABSOLUTE "${DECKLINK_SDK_DIR}")
  set(DECKLINK_SDK_DIR "${CMAKE_SOURCE_DIR}/${DECKLINK_SDK_DIR}")
endif()

set(_bindings_sources src/pydecklink_ext/bindings.cpp)
set(_sdk_bind_sources
  src/pydecklink_ext/bind_enums.cpp
  src/pydecklink_ext/bind_device.cpp
  src/pydecklink_ext/bind_format.cpp
  src/pydecklink_ext/bind_output.cpp
  src/pydecklink_ext/bind_input.cpp
  src/pydecklink_ext/bind_allocator.cpp
  src/pydecklink_ext/bind_api_info.cpp
  src/pydecklink_ext/bind_profile.cpp
)

if(WIN32 AND EXISTS "${DECKLINK_SDK_DIR}/DeckLinkAPI.idl")
  # Windows: generate headers from IDL via midl, link COM stubs.
  set(HAVE_DECKLINK_SDK TRUE)

  find_program(MIDL_EXECUTABLE midl
    HINTS "$ENV{WindowsSdkVerBinPath}/x64"
          "C:/Program Files (x86)/Windows Kits/10/bin/${CMAKE_VS_WINDOWS_TARGET_PLATFORM_VERSION}/x64"
  )
  if(NOT MIDL_EXECUTABLE)
    message(FATAL_ERROR "midl.exe not found — install the Windows SDK or run from a VS developer prompt")
  endif()

  set(_midl_output_dir "${CMAKE_CURRENT_BINARY_DIR}/decklink_generated")
  file(MAKE_DIRECTORY "${_midl_output_dir}")

  add_custom_command(
    OUTPUT "${_midl_output_dir}/DeckLinkAPI.h"
           "${_midl_output_dir}/DeckLinkAPI_i.c"
    COMMAND "${MIDL_EXECUTABLE}"
      /h "${_midl_output_dir}/DeckLinkAPI.h"
      /iid "${_midl_output_dir}/DeckLinkAPI_i.c"
      /env x64
      /W1 /char signed /robust
      "${DECKLINK_SDK_DIR}/DeckLinkAPI.idl"
    DEPENDS "${DECKLINK_SDK_DIR}/DeckLinkAPI.idl"
    COMMENT "Running MIDL on DeckLinkAPI.idl"
    VERBATIM
  )
  add_custom_target(decklink_midl DEPENDS
    "${_midl_output_dir}/DeckLinkAPI.h"
    "${_midl_output_dir}/DeckLinkAPI_i.c"
  )

  list(APPEND _bindings_sources
    "${_midl_output_dir}/DeckLinkAPI_i.c"
    ${_sdk_bind_sources}
  )
elseif(EXISTS "${DECKLINK_SDK_DIR}/DeckLinkAPIDispatch.cpp")
  # Linux / macOS: use the dispatch source provided by the SDK.
  set(HAVE_DECKLINK_SDK TRUE)
  list(APPEND _bindings_sources
    "${DECKLINK_SDK_DIR}/DeckLinkAPIDispatch.cpp"
    ${_sdk_bind_sources}
  )
else()
  message(STATUS "DeckLink SDK not found — building without SDK support")
  set(HAVE_DECKLINK_SDK FALSE)
endif()

nanobind_add_module(_bindings STABLE_ABI ${_bindings_sources})
target_include_directories(_bindings PRIVATE "${CMAKE_SOURCE_DIR}/src/pydecklink_ext")
if(HAVE_DECKLINK_SDK)
  target_compile_definitions(_bindings PRIVATE HAVE_DECKLINK_SDK)
  if(WIN32)
    # midl-generated DeckLinkAPI.h must be found first.
    add_dependencies(_bindings decklink_midl)
    target_include_directories(_bindings PRIVATE "${_midl_output_dir}")
    target_link_libraries(_bindings PRIVATE ole32 oleaut32)
  endif()
  target_include_directories(_bindings PRIVATE "${DECKLINK_SDK_DIR}")
  if(APPLE)
    target_link_libraries(_bindings PRIVATE "-framework CoreFoundation")
  endif()
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
