"""
fprime.build.cmake:

File to contain basic wrappers for the CMake. This will enable basic CMake commands in order to detect the properties of
the build. This should not be imported in-person, but rather should be included by the build package. This can be the
receiver of these delegated functions.

@author mstarch
"""
import os
import re
import sys
import shutil
import tempfile
import functools
import subprocess

# Get a cache directory for building CMakeList file, if need and remove at exit
import atexit

class CMakeBuildCache(object):
    """
    Builds CMake deployment for the purposes of inspecting that build. This exists because generating a build on every
    call take a long time. This cache will hold the results to prevent recalculation.
    """
    def __init__(self):
        """ Sets up the known project to None """
        self.project = None
        self.tempdir = None

    def get_cmake_temp_build(self, proj_dir):
        """ Gets a CMake build directory for the specified proj_dir """
        if self.project is not None and self.project != proj_dir:
            raise CMakeException("Already tracking project {}".format(self.project))
        self.project = proj_dir
        # No tempdir, prepare a build
        if self.tempdir is None:
            # Create a temp directory and register its deletion at the end of the program run
            self.tempdir = tempfile.mkdtemp()
            atexit.register(lambda: shutil.rmtree(self.tempdir, ignore_errors=True))
            # Turn that directory into a CMake build
            CMakeHandler._run_cmake(["-B", self.tempdir, "-S", self.project], write_override=True)
        return self.tempdir


class CMakeHandler(object):
    """
    CMake handler interacts with an F prime CMake-based system. This will help us interact with CMake in refined ways.
    """
    CMAKE_DEFAULT_BUILD_NAME = "build-fprime-automatic-{}"

    def __init__(self):
        """
        Instantiate a basic CMake handler.
        """
        self.build_cache = CMakeBuildCache()

    def execute_known_target(self, target, build_dir, path):
        """
        Executes a known target for a given build_dir. Path will default to a known path.
        :param build_dir: build_dir to use to run this.
        :param target: target to execute at the path, using above build_dir
        :param path: path to run target against. (default) current working directory
        :return: return code from CMake
        """
        # Get module name from the relative path to include root
        module = os.path.relpath(path, self.get_include_root(path, build_dir)).replace(os.sep, "_")
        cmake_target = module if target == "" else "{}_{}".format(module, target)
        return CMakeHandler._run_cmake(["--build", build_dir, "--target", cmake_target], write_override=True)

    def find_nearest_standard_build(self, platform, path):
        """
        Recurse up the directory tree from the given path, looking for a directory that matches the standard name. This
        will return that path, or error if one cannot be found.
        :return: path of nearest standard build directory
        :throws CMakeInvalidBuildException, a build was found but not setup, CMakeOrphanException, no build was found
        """
        path = os.path.abspath(path)
        # Get current directory to be checked, by removing file if path is not already a directory
        current = path if os.path.isdir(path) else os.path.dirname(path)
        # Look for a potential build that is valid
        potential_build = os.path.join(current, CMakeHandler.CMAKE_DEFAULT_BUILD_NAME.format(platform))
        if os.path.exists(potential_build):
            CMakeHandler._cmake_validate_build_dir(potential_build)
            return potential_build
        # Check for root, and throw error if it is already a root
        new_dir = os.path.dirname(current)
        if new_dir == path:
            raise CMakeException("{} not in ancestor tree"
                                 .format(CMakeHandler.CMAKE_DEFAULT_BUILD_NAME.format(platform)))
        return self.find_nearest_standard_build(platform, new_dir)

    def get_include_root(self, path, build_dir=None, project_dir=None):
        """
        Calculates the include root of the given path. The include root is defined as the following based on the other
        two values supplied. First, the following two path values are established:
           - Location of the project's root. This is defined in the project_dir's CMakeList.txt, or in the CMake Cache.
           - Location of the project's F prime checkout. This is defined in the same places.
        From there, the include root of the supplied path is whichever of those two paths is your parent. In cases where
        both are parents, it will take the outer-most parent
        :param path: path to calculate looking for include-root
        :param build_dir: directory of the CMake build
        :param project_dir: path to folder containing a CMakeList.txt defining an F prime project
        :return: include root for the given path.
        """
        path = path if os.path.abspath(path) is not None else os.path.abspath(os.getcwd())
        # Cannot handle both project_dir and build_dir
        if build_dir is not None and project_dir is not None:
            raise Exception("Cannot calculate build root from both project CMakeLists.txt and build_dir")
        # Detect which directory to use for these values, a temp build from a project or a formal build dir
        # !!! Note: using a project will cause file-system side effects, and take time if this is the first call !!!
        cache_dir = build_dir if build_dir is not None else self.build_cache.get_cmake_temp_build(project_dir)
        # Read cache fields for each possible directory the build_dir, and the new tempdir
        fields = ["FPRIME_FRAMEWORK_PATH", "FPRIME_PROJECT_ROOT"]
        possible_parents = list(filter(lambda parent: parent is not None,
                                       CMakeHandler._read_values_from_cache(fields, cache_dir)))
        # Check there is some possible parent
        if not possible_parents:
            raise CMakeProjectException(build_dir if cache_dir == build_dir else project_dir,
                                        "Does not define cache fields: {}".format(",".join(fields)))
        full_parents = map(os.path.abspath, possible_parents)
        # Parents *are* the common prefix for their children
        parents = list(filter(lambda parent: os.path.commonprefix([parent, path]) == parent, full_parents))
        # Check that a parent is the true parent
        if not parents:
            raise CMakeOrphanException(path)
        return parents[-1] # Take the last parent, project root


    @staticmethod
    def _read_values_from_cache(keys, build_dir):
        """
        Reads set values from cache into an output tuple.
        :param keys: keys to read in iterable
        :param build_dir: build directory containing cache file
        :return: a tuple of keys, None if not part of cache
        """
        cache = CMakeHandler._read_cache(build_dir)
        # Reads cache values suppressing KeyError, {}.get(x, default=None)
        miner = lambda x: cache.get(x, None)
        return tuple(map(miner, keys))

    @staticmethod
    def _read_cache(build_dir):
        """
        Reads the cache from the associated build_dir. This will return a dictionary of cache variable name to
        its value. This will not update internal state.
        :param build_dir: build directory to harvest for cache variables
        :return: {<cmake cache variable>: <cmake cache value>}
        """
        reg = re.compile("([^:]+):[^=]*=(.*)")
        # Check that the build_dir is properly setup
        CMakeHandler._cmake_validate_build_dir(build_dir)
        stdout, stderr = CMakeHandler._run_cmake(["-B", build_dir, "-LA"], capture=True)
        # Scan for lines in stdout that have non-None matches for the above regular expression
        valid_matches = filter(lambda item: item is not None, map(reg.match, stdout.split("\n")))
        # Return the dictionary composed from the match groups
        return dict(map(lambda match: (match.group(1), match.group(2)), valid_matches))

    @staticmethod
    def _cmake_validate_build_dir(build_dir):
        """
        Raises an exception if the build dir is not a valid CMake build directory
        :param build_dir: build_dir to validate
        """
        cache_file = os.path.join(build_dir, "CMakeCache.txt")
        if not os.path.isfile(cache_file):
            raise CMakeInvalidBuildException(build_dir)

    @staticmethod
    def _run_cmake(arguments, capture=False, write_override=False):
        """
        Will run the cmake system supplying the given arguments. Assumes that the CMake executable is somewhere on the
        path in order for this to run.
        :param arguments: arguments to supply to CMake.
        :param write_override: allows for non-read-only commands
        :return: (stdout, stderr)
        Note: !!! this function has potential File System side-effects !!!
        """
        # Keep these steps atomic
        cargs = ["cmake"]
        if not write_override:
            cargs.append("-N")
        cargs.extend(arguments)
        proc = subprocess.Popen(cargs, stdout=subprocess.PIPE if capture else None,
                                stderr=subprocess.PIPE if capture else None)
        stdout, stderr = proc.communicate()
        # Check for Python 3, and decode if possible
        if capture and sys.version_info[0] >= 3:
            stdout = stdout.decode()
            stderr = stderr.decode()
        # Raise for errors
        if proc.returncode != 0:
            raise CMakeExecutionException("CMake erred with return code {}".format(proc.returncode), stderr)
        return stdout, stderr


class CMakeException(Exception):
    """ Error occurred within this CMake package """
    pass


class CMakeInconsistencyException(CMakeException):
    """ Project CMakeLists.txt is inconsistent with build dir """
    def __init__(self, project_cmake, build_dir):
        """ Force an appropriate message """
        super(CMakeInconsistencyException, self).__init__("{} is inconsistent with build {}. Regenerate the build"
                                                          .format(project_cmake, build_dir))


class CMakeOrphanException(CMakeException):
    """ File is not managed by CMake project """
    def __init__(self, file_dir):
        """ Force an appropriate message """
        super(CMakeOrphanException, self).__init__("{} is outside the F prime project".format(file_dir))


class CMakeProjectException(CMakeException):
    """ Invalid project directory """
    def __init__(self, project_dir, error):
        """ Force an appropriate message """
        super(CMakeProjectException, self)\
            .__init__("{} is an invalid F prime deployment. {}".format(project_dir, error))


class CMakeInvalidBuildException(CMakeException):
    """ The supplied build directory was not setup as a CMake value """
    def __init__(self, build_dir):
        """ Force an appropriate message """
        super(CMakeInvalidBuildException, self)\
            .__init__("{} is not a CMake build directory. Please setup using 'cmake -B {} <path to deployment>'"
                      .format(build_dir, build_dir))


class CMakeExecutionException(CMakeException):
    """ Pass up a CMake Error as an Exception """
    def __init__(self, message, stderr):
        """ The error data should be stored """
        super(CMakeExecutionException, self).__init__(message)
        self.stderr = stderr

    def get_errors(self):
        """
        Returns the error stream data to the caller
        :return: stderr of CMake as supplied into this Exception
        """
        return self.stderr