# Force WITH_IPP=OFF on all platforms. On MSVC the upstream recipe used
# WITH_IPP=ON, which pulls Intel IPP-ICV (an external static asset OpenCV
# downloads at configure time). opencv_world<ver>.lib then references
# `ippicv*` / `ippiw*` symbols, but the IPP-ICV .lib is not exposed in
# OpenCV_LIBS and is not exported to consumers — orca-slicer's final link
# fails with hundreds of `error LNK2001: unresolved external symbol
# ippicvi*`. SkipPartCanvas.cpp is the sole cv:: consumer and does not
# rely on IPP-accelerated paths; turning IPP off across the board avoids
# carrying an extra static library through the whole link chain.
set(_use_IPP "-DWITH_IPP=OFF")

if (IN_GIT_REPO)
    set(OpenCV_DIRECTORY_FLAG --directory ${BINARY_DIR_REL}/dep_OpenCV-prefix/src/dep_OpenCV)
endif ()

orcaslicer_add_cmake_project(OpenCV
    URL https://github.com/opencv/opencv/archive/refs/tags/4.6.0.tar.gz
    URL_HASH SHA256=1ec1cba65f9f20fe5a41fda1586e01c70ea0c9a6d7b67c9e13edf0cfe2239277
    PATCH_COMMAND git apply ${OpenCV_DIRECTORY_FLAG} --verbose --ignore-space-change --whitespace=fix ${CMAKE_CURRENT_LIST_DIR}/0001-vs.patch  ${CMAKE_CURRENT_LIST_DIR}/0002-clang19-macos.patch
    CMAKE_ARGS
    -DBUILD_SHARED_LIBS=0
       -DBUILD_PERE_TESTS=OFF
       -DBUILD_TESTS=OFF
       -DBUILD_opencv_python_tests=OFF
       -DBUILD_EXAMPLES=OFF
       -DBUILD_JASPER=OFF
       -DBUILD_JAVA=OFF
       -DBUILD_JPEG=ON
       -DBUILD_APPS_LIST=version
       -DBUILD_opencv_apps=OFF
       -DBUILD_opencv_java=OFF
       -DBUILD_OPENEXR=OFF
       -DBUILD_PNG=ON
       -DBUILD_TBB=OFF
       -DBUILD_WEBP=OFF
       -DBUILD_ZLIB=OFF
       # Force OpenCV to use its internal libpng (BUILD_PNG=ON above)
       # instead of the host's system libpng. On CI runners with
       # libpng16-dev preinstalled, find_package(PNG) inside OpenCV
       # would otherwise bind grfmt_png.cpp.o to libpng16.so's versioned
       # symbols (png_read_update_info@@PNG16_0), which the static
       # deps libpng.a (no SONAME) cannot satisfy at final link time.
       -DCMAKE_DISABLE_FIND_PACKAGE_PNG=ON
       # Drop libtiff entirely. cv::imread is used in exactly one place
       # (SkipPartCanvas.cpp) and only reads PNG. WITH_TIFF=ON pulled
       # grfmt_tiff.cpp.o into libopencv_world.a, which then required
       # _TIFFOpen/_TIFFGetField/... at link time — on the macOS x86_64
       # runner only the arm64-only /opt/homebrew/lib/libtiff.dylib is
       # available (ld ignores it), and we don't want a system runtime
       # dep on Linux either.
       -DWITH_TIFF=OFF
       -DWITH_1394=OFF
       -DWITH_CUDA=OFF
       -DWITH_EIGEN=OFF
       ${_use_IPP}
       -DWITH_ITT=OFF
       -DWITH_FFMPEG=OFF
       -DWITH_GPHOTO2=OFF
       -DWITH_GSTREAMER=OFF
       -DOPENCV_GAPI_GSTREAMER=OFF
       -DWITH_GTK_2_X=OFF
       -DWITH_JASPER=OFF
       -DWITH_LAPACK=OFF
       -DWITH_MATLAB=OFF
       -DWITH_MFX=OFF
       -DWITH_DIRECTX=OFF
       -DWITH_DIRECTML=OFF
       -DWITH_OPENCL=OFF
       -DWITH_OPENCL_D3D11_NV=OFF
       -DWITH_OPENCLAMDBLAS=OFF
       -DWITH_OPENCLAMDFFT=OFF
       -DWITH_OPENEXR=OFF
       -DWITH_OPENJPEG=OFF
       -DWITH_QUIRC=OFF
       -DWITH_VTK=OFF
       -DWITH_JPEG=OFF
       -DWITH_WEBP=OFF
       -DENABLE_PRECOMPILED_HEADERS=OFF
       -DINSTALL_TESTS=OFF
       -DINSTALL_C_EXAMPLES=OFF
       -DINSTALL_PYTHON_EXAMPLES=OFF
       -DOPENCV_GENERATE_SETUPVARS=OFF
       -DOPENCV_INSTALL_FFMPEG_DOWNLOAD_SCRIPT=OFF
       -DBUILD_opencv_python2=OFF
       -DBUILD_opencv_python3=OFF
       -DWITH_OPENVINO=OFF
       -DWITH_INF_ENGINE=OFF
       -DWITH_NGRAPH=OFF
       -DBUILD_WITH_STATIC_CRT=OFF#set /MDd /MD
       -DBUILD_LIST=core,imgcodecs,imgproc,world
       -DBUILD_opencv_highgui=OFF
       -DWITH_ADE=OFF
       -DBUILD_opencv_world=ON
       -DWITH_PROTOBUF=OFF
       -DWITH_WIN32UI=OFF
       -DHAVE_WIN32UI=FALSE
)

