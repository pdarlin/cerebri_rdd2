# SPDX-License-Identifier: Apache-2.0
# Replace only this translation unit, only for the optional timing build.
# Zephyr and its manifest pin remain unchanged. Defer until its driver target
# has been populated, then retain all of that target's flags and include paths.
function(rdd2_instrument_imu_gpio)
  set(_driver drivers__sensor__tdk__icm45686)
  if(NOT TARGET ${_driver})
    message(FATAL_ERROR "gpio-timing requires the pinned ICM45686 driver target")
  endif()
  get_target_property(_source_dir ${_driver} SOURCE_DIR)
  get_target_property(_sources ${_driver} SOURCES)
  set(_original "${ZEPHYR_BASE}/drivers/sensor/tdk/icm45686/icm45686_stream.c")
  set(_output "${PROJECT_BINARY_DIR}/generated/gpio-timing/icm45686_stream.c")
  set(_script "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../scripts/prepare_imu_gpio_timing.py")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_original}" "${_script}")
  execute_process(
    COMMAND "${PYTHON_EXECUTABLE}" "${_script}" "${_original}" "${_output}"
    RESULT_VARIABLE _result
    ERROR_VARIABLE _error
  )
  if(NOT _result EQUAL 0)
    message(FATAL_ERROR "Cannot prepare pinned IMU timing driver: ${_error}")
  endif()
  set(_new_sources)
  set(_replaced 0)
  foreach(_source IN LISTS _sources)
    get_filename_component(_absolute "${_source}" ABSOLUTE BASE_DIR "${_source_dir}")
    if(_absolute STREQUAL _original)
      list(APPEND _new_sources "${_output}")
      math(EXPR _replaced "${_replaced} + 1")
    else()
      list(APPEND _new_sources "${_source}")
    endif()
  endforeach()
  if(NOT _replaced EQUAL 1)
    message(FATAL_ERROR "Expected exactly one ICM45686 stream source, got ${_replaced}")
  endif()
  set_property(TARGET ${_driver} PROPERTY SOURCES "${_new_sources}")
  target_include_directories(${_driver} PRIVATE "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../src")
  message(STATUS "gpio-timing: building verified instrumented IMU source ${_output}")
endfunction()

cmake_language(DEFER DIRECTORY "${CMAKE_SOURCE_DIR}" CALL rdd2_instrument_imu_gpio)
