/*****************************************************************************
*
*            (C) Copyright 1995-2005 The Board of Trustees of the
*                        University of Illinois
*                         All Rights Reserved
*
******************************************************************************/

/*****************************************************************************
* RCS INFORMATION:
*
*       $RCSfile: qPair.h,v $
*       $Author: kvandivo $        $Locker:  $             $State: Exp $
*       $Revision: 1.1 $           $Date: 2009/03/31 17:00:34 $
*
******************************************************************************/

// $Id: qPair.h,v 1.1 2009/03/31 17:00:34 kvandivo Exp $

#ifndef QPAIR_H
#define QPAIR_H

#include "version.h"

int parseArgs(int argc, char** argv);
void printUsage(int argc, char** argv);
void printCopyright(int argc, char** argv);
StructureAlignment* readStructureAlignment(char* fastaFilename, char* inputDir);

#endif
