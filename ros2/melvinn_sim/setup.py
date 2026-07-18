from setuptools import find_packages, setup

package_name = "melvinn_sim"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", ["launch/sim.launch.py"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Alan Castro",
    maintainer_email="alanaxelcastroresendiz@gmail.com",
    description="Kinematic simulation of MELVINN driven from /cmd_vel.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "fake_drive = melvinn_sim.fake_drive:main",
        ],
    },
)
