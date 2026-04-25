# orcabelt-fluidd-host — isolated WebKitGTK subprocess for the Device tab.
# Keeps libjavascriptcoregtk out of Orca's main process to avoid JSC SIGSEGV
# on first WebView load after a slice.

find_package(PkgConfig REQUIRED)
pkg_check_modules(ORCABELT_WEBKIT IMPORTED_TARGET webkit2gtk-4.1)

if(NOT ORCABELT_WEBKIT_FOUND)
    message(STATUS "orcabelt-fluidd-host: webkit2gtk-4.1 not found — skipping")
    return()
endif()

add_executable(orcabelt-fluidd-host main.cpp)
target_link_libraries(orcabelt-fluidd-host PRIVATE PkgConfig::ORCABELT_WEBKIT)
set_target_properties(orcabelt-fluidd-host PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/src/$<CONFIG>"
)

install(TARGETS orcabelt-fluidd-host
    RUNTIME DESTINATION bin
)
