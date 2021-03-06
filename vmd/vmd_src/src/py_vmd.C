#include "py_commands.h"
#include "vmd.h"
#include "DisplayDevice.h"
#include "UIText.h"


#include <tcl.h>

#if PY_MAJOR_VERSION < 3
extern "C" {
  void initvmd();
}
#endif

static PyObject *py_vmdupdate(PyObject *self, PyObject *args) {
  VMDApp *app = get_vmdapp();
  if (!app) {
    fprintf(stderr, "no app!!\n");
    Py_INCREF(Py_None);
    return Py_None;
  }
  return Py_BuildValue("i", app->VMDupdate(1));
}

static PyObject *py_vmdexit(PyObject *self, PyObject *args) {
  char *msg;
  int code = 0;
  int pauseseconds = 0;
  if (!PyArg_ParseTuple(args, "s|ii", &msg, &code, &pauseseconds))
    return NULL;
  VMDApp *app = get_vmdapp();
  app->VMDexit(msg, code, pauseseconds);
  // don't call VMDshutdown, because calling Tcl_Finalize() crashes Tkinter
  // Maybe add a callback to the Python atexit module?
  Py_INCREF(Py_None);
  return Py_None;
}

static PyObject *py_evaltcl(PyObject *self, PyObject *args) {
  char *cmd;
  if (!PyArg_ParseTuple(args, "s", &cmd)) return NULL;
  VMDApp *app = get_vmdapp();
  Tcl_Interp *interp = app->uiText->get_tcl_interp(); // THIS FAILS
  if (Tcl_Eval(interp, cmd) != TCL_OK) {
    PyErr_SetString(PyExc_ValueError, Tcl_GetStringResult(interp));
    return NULL;
  }
#if PY_MAJOR_VERSION >= 3
  return PyUnicode_FromString(Tcl_GetStringResult(interp));
#else
  return PyString_FromString(Tcl_GetStringResult(interp));
#endif
}

static PyMethodDef VMDAppMethods [] = {
    { (char *)"VMDupdate", py_vmdupdate, METH_VARARGS },
    { (char *)"VMDexit", py_vmdexit, METH_VARARGS },
    { (char *)"VMDevaltcl", py_evaltcl, METH_VARARGS },
    {NULL, NULL, 0, NULL}
};

static VMDApp *the_app=NULL;
static PyThreadState *event_tstate = NULL;

static int vmd_input_hook() {
  if (the_app) {
    the_app->VMDupdate(1);
  }
  PyEval_RestoreThread(event_tstate);
  PyRun_SimpleString(
      "try:\n"
      "\timport Tkinter\n"
      "\twhile Tkinter.tkinter.dooneevent(Tkinter.tkinter.DONT_WAIT):\n"
      "\t\tpass\n"
      "except:\n"
      "\tpass\n");
  PyEval_SaveThread();
  return 0;
}

#if PY_MAJOR_VERSION >= 3
static struct PyModuleDef vmddef = {
    PyModuleDef_HEAD_INIT,
    "vmd",
    NULL,
    -1,
    VMDAppMethods,
};

#define INITERROR return NULL

PyMODINIT_FUNC PyInit_vmd(void) {
#else
#define INITERROR return
void initvmd() {
#endif
  // Assume that VMD should not initialize or use MPI
  // It is conceivable we would want to be able to load the VMD
  // Python module into a MPI-based Python run, and enable the
  // MPI features of VMD, but we'll have to determine the best way
  // to detect this and it will need to be tested since we may have
  // to handle this case differently than the normal MPI case where
  // VMD explicitly does MPI initialization and shutdown itself.
  int mpienabled = 0;

  // If there's already a VMDapp in get_vmdapp, then we must be running
  // inside a standalone VMD instead of being loaded as a python extension.
  // Don't throw an error - just load the methods for interoperability
  // in case vmd.so is in the PYTHONPATH of the standalone application.
  if (get_vmdapp() != NULL) {
#if PY_MAJOR_VERSION >= 3
    return PyModule_Create(&vmddef);
#else
    (void)Py_InitModule((char *)"vmd", VMDAppMethods);
    return;
#endif
  }

  int argc=1;
  char **argv = (char**)malloc(sizeof(char*));
  argv[0] = (char*) Py_GetProgramFullPath();
  if (!VMDinitialize(&argc, (char ***) &argv, mpienabled)) {
    INITERROR;
  }

  // XXX this is a hack, and it would be better to tie this into
  //     VMDApp more directly at some later point, but the regular
  //     VMD startup code is similarly lame, so we'll use it for now.
  const char *disp = getenv("VMDDISPLAYDEVICE");
  if (!disp) disp="text";

  int loc[2] = { 50, 50 };
  int size[2] = { 400, 400 };
  VMDgetDisplayFrame(loc, size);

  VMDApp *app = new VMDApp(1, argv, mpienabled);
  app->VMDinit(1, argv, disp, loc, size);

  // read application defaults
  VMDreadInit(app);

  // read user-defined startup files
  VMDreadStartup(app);

  set_vmdapp(app);

  // set my local static
  the_app = app;

#if PY_MAJOR_VERSION >= 3
  PyObject *vmdmodule = PyModule_Create(&vmddef);
#else
  PyObject *vmdmodule = Py_InitModule((char *)"vmd", VMDAppMethods);
#endif

// This array of function pointers initializes all of the modules
PyObject* (*initializers[])(void) = {
  initaxes,
  initanimate,
  initatomsel,
  initcolor,
  initdisplay,
  initgraphics,
  initimd,
  initlabel,
  initmaterial,
  initmeasure,
  initmolecule,
  initmolrep,
  initmouse,
  initrender,
  inittrans,
  inittopology,
  initvmdmenu,
#ifdef VMDNUMPY
  initvmdnumpy,
#endif
};

const char *modules[] = {
    "axes", "animate", "atomsel", "color", "display", "graphics",
    "imd", "label", "material", "measure", "molecule", "molrep",
    "mouse", "render", "trans", "topology", "vmdmenu", "vmdnumpy"
};

#if (PY_MAJOR_VERSION == 2) && (PY_MINOR_VERSION < 5)
#define CAST_HACK (char *)
#else
#define CAST_HACK
#endif

for (unsigned i=0; i<sizeof(initializers)/sizeof(void(*)(void)); i++) {
  PyObject *module = (*initializers[i])();
  if (!module) INITERROR;
  int retval = PyModule_AddObject(vmdmodule, CAST_HACK modules[i], module);
  if (retval) INITERROR;
}

  event_tstate = PyThreadState_Get();
#if defined(VMD_SHARED)
  PyOS_InputHook = vmd_input_hook;
#endif

#if PY_MAJOR_VERSION >= 3
  return vmdmodule;
#endif
}

