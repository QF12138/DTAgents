cmake -G "Visual Studio 18 2026" -Wno-dev -A "x64" -B build-msvc -S . ^
      -DCMAKE_PREFIX_PATH=D:/DTGeoStudio/vgedt/Library ^
      -DSDK_INSTALL_PATH=D:/DTGeoStudio/install ^
      -DAPP_INSTALL_PATH=D:/DTGeoStudio