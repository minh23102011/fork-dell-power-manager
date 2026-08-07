cmake_minimum_required(VERSION 3.24)
project(powerdeck-native VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 6.6 REQUIRED COMPONENTS Core DBus Widgets)

qt_add_executable(powerdeck-native
    src/main.cpp
    src/mainwindow.cpp
    src/mainwindow.hpp
)

target_compile_options(powerdeck-native PRIVATE
    -Wall
    -Wextra
    -Wpedantic
    -Wconversion
    -Wshadow
)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(powerdeck-native PRIVATE
        $<$<CONFIG:Release>:-ffunction-sections>
        $<$<CONFIG:Release>:-fdata-sections>
    )
    target_link_options(powerdeck-native PRIVATE
        $<$<CONFIG:Release>:-Wl,--gc-sections>
        $<$<CONFIG:Release>:-Wl,--as-needed>
    )
endif()

include(CheckIPOSupported)
check_ipo_supported(RESULT powerdeck_ipo_supported OUTPUT powerdeck_ipo_error)
if(powerdeck_ipo_supported)
    set_property(TARGET powerdeck-native PROPERTY INTERPROCEDURAL_OPTIMIZATION_RELEASE TRUE)
endif()

target_link_libraries(powerdeck-native PRIVATE
    Qt6::Core
    Qt6::DBus
    Qt6::Widgets
)

install(TARGETS powerdeck-native RUNTIME DESTINATION bin)
