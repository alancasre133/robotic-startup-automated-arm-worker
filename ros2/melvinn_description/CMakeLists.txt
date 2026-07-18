cmake_minimum_required(VERSION 3.8)
project(melvinn_description)

find_package(ament_cmake REQUIRED)

# Nothing to compile — this package is data (URDF) plus launch files.
install(DIRECTORY urdf launch rviz
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
