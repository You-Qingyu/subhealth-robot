from setuptools import find_packages, setup


package_name = 'physio_mock_publisher'

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
    description='Deterministic mock physiological sensor publisher.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'physio_mock_publisher_node = physio_mock_publisher.node:main',
        ],
    },
)
