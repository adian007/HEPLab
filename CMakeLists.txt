cmake_minimum_required(VERSION 3.25)

project(HEPLabWorkbench VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

option(HEPLAB_BUILD_TESTS "Build HEPLab desktop tests" ON)

find_package(Qt6 6.8 REQUIRED COMPONENTS Core Gui Widgets Test OpenGL OpenGLWidgets)

enable_testing()
add_subdirectory(desktop)
