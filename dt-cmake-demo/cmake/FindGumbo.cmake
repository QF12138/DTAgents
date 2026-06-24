# Find the Gumbo library (libGumbo).
# Imported targets
# ^^^^^^^^^^^^^^^^
#
# This module defines the following :prop_tgt:`IMPORTED` targets:
#
# ``Gumbo::Gumbo``
#   The Gumbo library, if found.
#
# Result variables
# ^^^^^^^^^^^^^^^^
#
# This module will set the following variables in your project:
#
# ``Gumbo_FOUND``
#   true if the Gumbo headers and libraries were found
# ``Gumbo_INCLUDE_DIR``
#   the directory containing the Gumbo headers
# ``Gumbo_INCLUDE_DIRS``
#   the directory containing the Gumbo headers
# ``Gumbo_LIBRARIES``
#   Gumbo libraries to be linked
#
# Cache variables
# ^^^^^^^^^^^^^^^
#
# The following cache variables may also be set:
#
# ``Gumbo_INCLUDE_DIR``
#   the directory containing the Gumbo headers
# ``Gumbo_LIBRARY``
#   the path to the Gumbo library

find_path(Gumbo_INCLUDE_DIR "gumbo.h")

set(Gumbo_NAMES ${Gumbo_NAMES} "gumbo" "libgumbo")
foreach(name ${Gumbo_NAMES})
  list(APPEND Gumbo_NAMES_DEBUG "${name}" "${name}d")
endforeach()

if(NOT Gumbo_LIBRARY)
  find_library(Gumbo_LIBRARY_RELEASE NAMES ${Gumbo_NAMES})
  find_library(Gumbo_LIBRARY_DEBUG NAMES ${Gumbo_NAMES_DEBUG})
  include(SelectLibraryConfigurations)
  select_library_configurations(Gumbo)
  mark_as_advanced(Gumbo_LIBRARY_RELEASE Gumbo_LIBRARY_DEBUG)
endif()
unset(Gumbo_NAMES)
unset(Gumbo_NAMES_DEBUG)

include(FindPackageHandleStandardArgs)
FIND_PACKAGE_HANDLE_STANDARD_ARGS(Gumbo
                                  REQUIRED_VARS Gumbo_LIBRARY Gumbo_INCLUDE_DIR
                                  VERSION_VAR Gumbo_VERSION_STRING)

if(Gumbo_FOUND)
  set(Gumbo_LIBRARIES ${Gumbo_LIBRARY})
  set(Gumbo_INCLUDE_DIRS "${Gumbo_INCLUDE_DIR}")

  if(NOT TARGET Gumbo::Gumbo)
    add_library(Gumbo::Gumbo UNKNOWN IMPORTED)
    if(Gumbo_INCLUDE_DIRS)
      set_target_properties(Gumbo::Gumbo PROPERTIES
        INTERFACE_INCLUDE_DIRECTORIES "${Gumbo_INCLUDE_DIRS}")
    endif()
    if(EXISTS "${Gumbo_LIBRARY}")
      set_target_properties(Gumbo::Gumbo PROPERTIES
        IMPORTED_LINK_INTERFACE_LANGUAGES "C"
        IMPORTED_LOCATION "${Gumbo_LIBRARY}")
    endif()
    if(EXISTS "${Gumbo_LIBRARY_RELEASE}")
      set_property(TARGET Gumbo::Gumbo APPEND PROPERTY
        IMPORTED_CONFIGURATIONS RELEASE)
      set_target_properties(Gumbo::Gumbo PROPERTIES
        IMPORTED_LINK_INTERFACE_LANGUAGES_RELEASE "C"
        IMPORTED_LOCATION_RELEASE "${Gumbo_LIBRARY_RELEASE}")
    endif()
    if(EXISTS "${Gumbo_LIBRARY_DEBUG}")
      set_property(TARGET Gumbo::Gumbo APPEND PROPERTY
        IMPORTED_CONFIGURATIONS DEBUG)
      set_target_properties(Gumbo::Gumbo PROPERTIES
        IMPORTED_LINK_INTERFACE_LANGUAGES_DEBUG "C"
        IMPORTED_LOCATION_DEBUG "${Gumbo_LIBRARY_DEBUG}")
    endif()
  endif()
endif()

mark_as_advanced(Gumbo_INCLUDE_DIR Gumbo_LIBRARY)
