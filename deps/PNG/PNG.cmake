if (APPLE)
    # Only disable NEON extension for Apple ARM builds, leave it enabled for Raspberry PI.
    set(_disable_neon_extension "-DPNG_ARM_NEON=off")
else ()
    set(_disable_neon_extension "")
endif ()

if(APPLE AND IS_CROSS_COMPILE)
# TODO: check if it doesn't create problem when compiling from arm to x86_64
    orcaslicer_add_cmake_project(PNG
        GIT_REPOSITORY https://github.com/glennrp/libpng.git
        GIT_TAG v1.6.35
        DEPENDS ${ZLIB_PKG}
        PATCH_COMMAND       ${GIT_EXECUTABLE} checkout -f -- . && git clean -df &&
                            ${GIT_EXECUTABLE} apply --whitespace=fix ${CMAKE_CURRENT_LIST_DIR}/macos-arm64.patch ${CMAKE_CURRENT_LIST_DIR}/0002-clang19-macos.patch
        CMAKE_ARGS
            -DPNG_SHARED=OFF
            -DPNG_STATIC=ON
            # PNG_PREFIX intentionally OMITTED. Upstream PrusaSlicer used
            # -DPNG_PREFIX=prusaslicer_ to namespace libpng symbols away from
            # any system libpng. OpenCV's grfmt_png.cpp.o (inside
            # libopencv_world.a) calls libpng with the standard `png_*` names,
            # not the prefixed ones — so a prefixed deps libpng cannot satisfy
            # opencv_world at final link. Other deps consumers (wxWidgets uses
            # `wxUSE_LIBPNG=sys` and reaches for system libpng instead, so it
            # is unaffected) rebuild against the unprefixed deps libpng.
            -DPNG_TESTS=OFF
            -DDISABLE_DEPENDENCY_TRACKING=OFF
            ${_disable_neon_extension}
    )
else ()
set(_patch_step "")
    if (APPLE)
        set(_patch_step PATCH_COMMAND ${PATCH_CMD} ${CMAKE_CURRENT_LIST_DIR}/PNG.patch ${CMAKE_CURRENT_LIST_DIR}/0002-clang19-macos.patch)
    endif ()
    orcaslicer_add_cmake_project(PNG
        # GIT_REPOSITORY https://github.com/glennrp/libpng.git
        # GIT_TAG v1.6.35
        URL https://github.com/glennrp/libpng/archive/refs/tags/v1.6.35.zip
        URL_HASH SHA256=3d22d46c566b1761a0e15ea397589b3a5f36ac09b7c785382e6470156c04247f
        DEPENDS ${ZLIB_PKG}
        "${_patch_step}"
        CMAKE_ARGS
            -DPNG_SHARED=OFF
            -DPNG_STATIC=ON
            # PNG_PREFIX intentionally OMITTED — see comment in the APPLE
            # IS_CROSS_COMPILE branch above. OpenCV's bundled grfmt_png.cpp
            # references the standard `png_*` symbol names; a prefixed deps
            # libpng would not satisfy them at the final orca-slicer link.
            -DPNG_TESTS=OFF
            -DDISABLE_DEPENDENCY_TRACKING=OFF
            ${_disable_neon_extension}
)
endif()

if (MSVC)
    add_debug_dep(dep_PNG)
endif ()
