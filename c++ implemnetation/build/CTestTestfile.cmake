# CMake generated Testfile for 
# Source directory: C:/Users/HP/aesh/SISP/c++ implemnetation
# Build directory: C:/Users/HP/aesh/SISP/c++ implemnetation/build
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
if(CTEST_CONFIGURATION_TYPE MATCHES "^([Dd][Ee][Bb][Uu][Gg])$")
  add_test(SISPTests "C:/Users/HP/aesh/SISP/c++ implemnetation/build/Debug/test_runner.exe")
  set_tests_properties(SISPTests PROPERTIES  _BACKTRACE_TRIPLES "C:/Users/HP/aesh/SISP/c++ implemnetation/CMakeLists.txt;57;add_test;C:/Users/HP/aesh/SISP/c++ implemnetation/CMakeLists.txt;0;")
elseif(CTEST_CONFIGURATION_TYPE MATCHES "^([Rr][Ee][Ll][Ee][Aa][Ss][Ee])$")
  add_test(SISPTests "C:/Users/HP/aesh/SISP/c++ implemnetation/build/Release/test_runner.exe")
  set_tests_properties(SISPTests PROPERTIES  _BACKTRACE_TRIPLES "C:/Users/HP/aesh/SISP/c++ implemnetation/CMakeLists.txt;57;add_test;C:/Users/HP/aesh/SISP/c++ implemnetation/CMakeLists.txt;0;")
elseif(CTEST_CONFIGURATION_TYPE MATCHES "^([Mm][Ii][Nn][Ss][Ii][Zz][Ee][Rr][Ee][Ll])$")
  add_test(SISPTests "C:/Users/HP/aesh/SISP/c++ implemnetation/build/MinSizeRel/test_runner.exe")
  set_tests_properties(SISPTests PROPERTIES  _BACKTRACE_TRIPLES "C:/Users/HP/aesh/SISP/c++ implemnetation/CMakeLists.txt;57;add_test;C:/Users/HP/aesh/SISP/c++ implemnetation/CMakeLists.txt;0;")
elseif(CTEST_CONFIGURATION_TYPE MATCHES "^([Rr][Ee][Ll][Ww][Ii][Tt][Hh][Dd][Ee][Bb][Ii][Nn][Ff][Oo])$")
  add_test(SISPTests "C:/Users/HP/aesh/SISP/c++ implemnetation/build/RelWithDebInfo/test_runner.exe")
  set_tests_properties(SISPTests PROPERTIES  _BACKTRACE_TRIPLES "C:/Users/HP/aesh/SISP/c++ implemnetation/CMakeLists.txt;57;add_test;C:/Users/HP/aesh/SISP/c++ implemnetation/CMakeLists.txt;0;")
else()
  add_test(SISPTests NOT_AVAILABLE)
endif()
