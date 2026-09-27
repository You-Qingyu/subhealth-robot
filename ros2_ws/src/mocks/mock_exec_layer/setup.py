from setuptools import find_packages, setup


package_name = 'mock_exec_layer'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Duck Ran',
    maintainer_email='puranlai@qq.com',
    description='Deterministic mock execution action server.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'mock_exec_layer_node = mock_exec_layer.node:main',
        ],
    },
)
