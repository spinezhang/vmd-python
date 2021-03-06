
from distutils import sysconfig
from distutils.core import setup
from distutils.util import convert_path
from distutils.command.build import build as DistutilsBuild
from distutils.cmd import Command
from subprocess import check_call, check_output
from glob import glob
import platform
import os

packages = ['vmd']

###############################################################################

class VMDBuild(DistutilsBuild):
    user_options = [
        ("debug", None, "Build with debug symbols"),
    ]

    def initialize_options(self):
        self.debug = False
        DistutilsBuild.initialize_options(self)

    #==========================================================================

    def finalize_options(self):
        if self.debug:
            print("Building with debug symbols")
            self.debug = True
        DistutilsBuild.finalize_options(self)

    #==========================================================================

    def run(self):
        # Run original build code
        DistutilsBuild.run(self)
        # Setup and run compilation script
        self.execute(self.compile_vmd, [], msg="Compiling VMD")

    #==========================================================================

    def compile_vmd(self):
        # Determine target to build
        target = self.get_vmd_build_target()
        srcdir = convert_path(os.path.dirname(os.path.abspath(__file__)) + "/vmd")
        builddir = convert_path(os.path.abspath(self.build_lib + "/vmd"))
        pydir = sysconfig.EXEC_PREFIX

        self.set_environment_variables(pydir)

        # Execute the build
        cmd = [
            os.path.join(srcdir, "install.sh"),
            target,
            builddir,
            pydir,
        ]
        check_call(cmd, cwd=srcdir)

    #==========================================================================

    @staticmethod
    def _find_include_dir(incfile, pydir=sysconfig.EXEC_PREFIX):
        """
        Finds the path containing an include file. Starts by searching
        $INCLUDE, then whatever system include paths gcc looks in.
        If it can't find the file, defaults to "$pydir/include"
        """

        # Look in directories specified by $INCLUDE
        searchdirs = [d for d in os.environ.get("INCLUDE", "").split(":")
                      if os.path.isdir(d)]
        # Also look in the directories gcc does
        try:
            out = check_output(r"echo | gcc -E -Wp,-v - 2>&1 | grep '^\s.*'",
                               shell=True)
            out = out.decode("utf-8").strip().split("\n")
            searchdirs.extend([d.strip() for d in out if os.path.isdir(d.strip())])
        except: pass
        searchdirs.insert(0, os.path.join(pydir, "include"))

        # Find the actual file
        out = b""
        try:
            out = check_output(["find", "-H"]
                               + searchdirs
                               + ["-maxdepth", "2",
                                  "-name", incfile],
                               close_fds=True,
                               stderr=open(os.devnull, 'wb'))
        except: pass

        incdir = os.path.split(out.decode("utf-8").split("\n")[0])[0]
        if not glob(os.path.join(incdir, incfile)): # Glob allows wildcards
            incdir = os.path.join(pydir, "include", incfile)
            print("\nWARNING: Could not find include file '%s' in standard "
                  "include directories.\n Defaulting to: '%s'"
                  % (incfile, incdir))
        print("   INC: %s -> %s" % (incfile, incdir))
        return incdir

    #==========================================================================

    @staticmethod
    def _find_library_dir(libfile, pydir=sysconfig.EXEC_PREFIX, fallback=True):
        """
        Finds the directory containing a library file. Starts by searching
        $LD_LIBRARY_PATH, then ld.so.conf system paths used by gcc.
        """

        # Look in python installation directory, then in directories
        # specified by $LD_LIBRARY_PATH
        out = b""
        if "Darwin" in platform.system():
            libfile = "%s.dylib" % libfile
            searchdirs = [d for d in os.environ.get("DYLD_LIBRARY_PATH",
                                                    "").split(":")
                          if os.path.isdir(d)]
        else:
            libfile = "%s.so" % libfile
            searchdirs = [d for d in os.environ.get("LD_LIBRARY_PATH",
                                                    "").split(":")
                          if os.path.isdir(d)]

        searchdirs.insert(0, os.path.join(pydir, "lib"))

        try:
            out = check_output(["find", "-H"]
                               + searchdirs
                               + ["-maxdepth", "1",
                                  "-name", libfile],
                               close_fds=True,
                               stderr=open(os.devnull, 'wb'))
        except: pass

        libdir = os.path.split(out.decode("utf-8").split("\n")[0])[0]
        if glob(os.path.join(libdir, libfile)): # Glob allows wildcards
            print("   LIB: %s -> %s" % (libfile, libdir))
            return libdir

        # See if the linker can find it, alternatively
        # This only works on Linux
        if "Linux" in platform.system():
            try:
                out = check_output("ldconfig -p | grep %s$" % libfile.replace("*",".*"), shell=True)
            except: pass
            libdir = os.path.split(out.decode("utf-8").split(" ")[-1])[0]

        # For OSX, use defaults + DYLD_FALLBACK_LIBRARY_PATH
        elif "Darwin" in platform.system():
            searchdirs = [os.path.join(os.environ.get("HOME", ""), "lib"),
                          "/usr/local/lib", "/usr/lib"]
            searchdirs = [d for d in set(searchdirs) if os.path.isdir(d)]
            try:
                print("  Searching %s" % " ".join(searchdirs))
                out = check_output(["find", "-H"]
                                   + searchdirs
                                   + ["-maxdepth", "1",
                                      "-name", libfile],
                                   close_fds=True,
                                   stderr=open(os.devnull, 'wb'))
            except: pass
            libdir = os.path.split(out.decode("utf-8").split("\n")[0])[0]
            if glob(os.path.join(libdir, libfile)):
                print("   LIB: %s -> %s" % (libfile, libdir))
                return libdir
        else:
            libdir = ""

        if not glob(os.path.join(libdir, libfile)):
            libdir = os.path.join(pydir, "lib")
            if not fallback:
                return None
            print("WARNING: Could not find library file '%s' in standard "
                  "library directories.\n Defaulting to: '%s'"
                  % (libfile, os.path.join(libdir, libfile)))
        print("   LIB: %s -> %s" % (libfile, libdir))
        return libdir

    #==========================================================================

    def _get_python_ldflag(self, pydir):
        """
        Hopefully obtains the path to and correct version for
        whatever libpython is currently running. Some of this is inspired
        from scikit-build's function for doing this.
        """
        # See if we can get it from sysconfig
        pylibname = sysconfig.get_config_var("LIBRARY") # "libpython3.6m.a"
        pylibdir = sysconfig.get_config_var("LIBDIR") # "~/miniconda/lib"
        pythonldflag = os.path.splitext(pylibname)[0] if pylibdir else None

        suffix = ".dylib" if "Darwin" in platform.system() else ".so"

        # Check a library with appropriate extension actually exists.
        # If not, try to find a libpython and use that
        if pylibname is None or pylibdir is None or \
                not os.path.isfile(os.path.join(pylibdir, pythonldflag)
                                   + suffix):

            print("Finding python location via fallback method...")
            pylibname = "libpython%s*" % sysconfig.get_python_version()
            candidate_libs = self._find_library_dir(pylibname)
            libs = sorted(glob(os.path.join(candidate_libs, pylibname)),
                          key=len)
            pylibdir, pythonldflag = os.path.split(libs[-1])
            # Remove trailing .so from pythonldflag
            pythonldflag = pythonldflag[:pythonldflag.index(suffix)]

        # Remove leading "lib" from pythonldflag
        pythonldflag = pythonldflag[3:]

        return "-L%s -l%s" % (pylibdir, pythonldflag)

    #==========================================================================

    def set_environment_variables(self, pydir):
        """
        Sets environment variables used by the build process.
        Tries to get relevant paths from sysconfig, and falls back
        to the usual python directory structure.
        """
        # First, clear environment variables. Do this explicitly here instead
        # of just assigning so that it is very obvious.
        os.environ["LDFLAGS"] = ""
        os.environ["CFLAGS"] = ""
        os.environ["CXXFLAGS"] = ""
        os.environ["INCLUDE"] = ""

        print("Finding libraries...")
        addir = sysconfig.get_config_var("LIBDIR")
        if addir is None: addir = os.path.join(pydir, "lib")

        # Linker looks for needed libraries in python directory
        os.environ["LDFLAGS"] += " -L%s" % addir
        # Linker looks for libraries *those* libraries need in python directory
        if "Linux" in platform.system():
            extra_ld_options=""
            # Uncommnent next line if your OS linker does not include math
            # library or other indirecly linked shared libraries by default
            # (e.g Ubuntu 11.04 or later). Developers should read 
            # https://wiki.ubuntu.com/NattyNarwhal/ToolchainTransition
            
            #extra_ld_options="--no-as-needed,"
            
            os.environ["LDFLAGS"] += " -Wl,%s-rpath-link,%s" % (extra_ld_options,addir)
        elif "Darwin" in platform.system():
            os.environ["LDFLAGS"] += " -headerpad_max_install_names"
            os.environ["LDFLAGS"] += " -Wl,-rpath,%s" % addir

        addir = sysconfig.get_config_var("INCLUDEDIR")
        if addir is None: addir = os.path.join(pydir, "include")
        os.environ["CFLAGS"] += " -I%s" % addir
        os.environ["CXXFLAGS"] += " -I%s" % addir

        # No reliable way to ask for actual available library, so try 8.5 first
        tcllibdir = self._find_library_dir("libtcl8.5", fallback=False)
        os.environ["TCLLDFLAGS"] = "-ltcl8.5"
        if tcllibdir is None:
            print("  Newer libtcl8.6 used")
            tcllibdir = self._find_library_dir("libtcl8.6")
            os.environ["TCLLDFLAGS"] = "-ltcl8.6"
        os.environ["TCL_LIBRARY_DIR"] = tcllibdir

        os.environ["TCL_INCLUDE_DIR"] = self._find_include_dir("tcl.h")
        os.environ["TCLLIB"] = "-L%s" % os.environ["TCL_LIBRARY_DIR"]
        os.environ["TCLINC"] = "-I%s" % os.environ["TCL_INCLUDE_DIR"]

        # Sqlite (for dmsplugin)
        os.environ["SQLITELIB"] = "-L%s" % self._find_library_dir("libsqlite3")
        os.environ["SQLITEINC"] = "-I%s" % self._find_include_dir("sqlite3.h")
        os.environ["SQLITELDFLAGS"] = "-lsqlite3"

        # Expat (for hoomdplugin)
        os.environ["EXPATLIB"] = "-L%s" % self._find_library_dir("libexpat")
        os.environ["EXPATINC"] = "-I%s" % self._find_include_dir("expat.h")
        os.environ["EXPATLDFLAGS"] = "-lexpat"

        # Netcdf (for netcdfplugin)
        os.environ["NETCDFLIB"] = "-L%s" % self._find_library_dir("libnetcdf")
        os.environ["NETCDFINC"] = "-I%s" % self._find_include_dir("netcdf.h")
        os.environ["NETCDFLDFLAGS"] = "-lnetcdf"
        os.environ["NETCDFDYNAMIC"] = "1"

        # Ask numpy where it is
        import numpy
        os.environ["NUMPY_INCLUDE_DIR"] = numpy.get_include()
        os.environ["NUMPY_LIBRARY_DIR"] = numpy.get_include().replace("include",
                                                                      "lib")

        os.environ["PYTHON_LIBRARY_DIR"] = sysconfig.get_python_lib()
        os.environ["PYTHON_INCLUDE_DIR"] = sysconfig.get_python_inc()

        # Get python linker flag, as it may be -l3.6m or -l3.6 depending on malloc
        # this python was built against
        pythonldflag = self._get_python_ldflag(pydir)

        os.environ["VMDEXTRALIBS"] = " ".join([os.environ["SQLITELDFLAGS"],
                                               os.environ["EXPATLDFLAGS"],
                                               pythonldflag])

        # Set debug variable for now if requested
        os.environ["DEBUG"] = "DEBUG" if self.debug else ""

    #==========================================================================

    @staticmethod
    def get_vmd_build_target():
        """
        Translates python's information on machine architecture into
        the correct build target string for VMD
        """

        osys = platform.system()
        mach = platform.machine()

        if "Linux" in osys:
            if "x86_64" in mach:
                target = "LINUXAMD64"
            else:
                target = "LINUX"
        elif "Darwin" in osys:
            if "x86_64" in mach:
                target = "MACOSXX86_64"
            elif "PowerPC" in mach:
                target = "MACOSX"
            else:
                target = "MACOSXX86"
        elif "Windows" in osys:
            if "64" in mach:
                target = "WIN64"
            else:
                target = "WIN32"
        else:
            raise ValueError("Unsupported os '%s' and machine '%s'" % (osys, mach))

        return target

###############################################################################

class VMDTest(Command):
    user_options = [("pytest-args=", "a", "Arguments to pass to pytest")]

    def initialize_options(self):
        self.pytest_args = ''
    def finalize_options(self):
        pass

    def run(self):
        import shlex
        import pytest
        errno = pytest.main(shlex.split(self.pytest_args))
        raise SystemExit(errno)

###############################################################################

setup(name='vmd-python',
      version='2.0.10',
      description='Visual Molecular Dynamics Python module',
      author='Robin Betz',
      author_email='robin@robinbetz.com',
      url='http://github.com/Eigenstate/vmd-python',
      license='VMD License',
      packages=['vmd'],
      package_data={'vmd' : ['libvmd.so']},
      cmdclass={
          'build': VMDBuild,
          'test': VMDTest,
      },
     )
