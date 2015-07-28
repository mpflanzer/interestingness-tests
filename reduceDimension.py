#!/usr/bin/env python3

import sys, os, re, openCLTest

def which(cmd):
    if sys.platform == 'win32' and '.' not in cmd:
        cmd += '.exe'

    if os.access(cmd, os.F_OK):
        return cmd

    for path in os.environ["PATH"].split(os.pathsep):
        if os.access(os.path.join(path, cmd), os.F_OK):
            return os.path.join(path, cmd)

    return None

class DimensionReducer:
    def __init__(self, kernelFile, kernelTest):
        self.kernelFile = open(kernelFile, 'r+')
        self.kernelTest = kernelTest
        kernelContent = self.kernelFile.read()

        m = re.search('//(.*) -g ([0-9]+),([0-9]+),([0-9]+) -l ([0-9]+),([0-9]+),([0-9]+)\n', kernelContent)

        if m:
            self.metaInformation = m.group(1)
            self.origGlobalDimensions = (m.group(2), m.group(3), m.group(4))
            self.origLocalDimensions = (m.group(5), m.group(6), m.group(7))
            self.kernelContent = kernelContent.replace(m.group(0), '')

    def __del__(self):
        self.kernelFile.close()

    def updateDimensions(self, globalDim, localDim):
        tmpGlobalDim = [0] * len(globalDim)

        for i in range(0, len(globalDim)):
            gDim = globalDim[i]
            lDim = localDim[i]

            while gDim % lDim != 0 and gDim <= self.globalDim[i]:
                gDim += 1

            tmpGlobalDim[i] = gDim

        return (tuple(tmpGlobalDim), localDim)

    def rewriteDimensions(self, globalDim, localDim):
        self.kernelFile.seek(0)
        self.kernelFile.truncate()
        self.kernelFile.write("//%s -g %d,%d,%d -l %d,%d,%d\n" % (self.metaInformation, globalDim[0], globalDim[1], globalDim[2], localDim[0], localDim[1], localDim[2]))
        self.kernelFile.write(self.kernelContent)
        self.kernelFile.flush()

    def reduce(self):
        newGlobalDim = (1,1,1)
        newLocalDim = (1,1,1)

        self.rewriteDimensions(newGlobalDim, newLocalDim)

        while(not self.kernelTest.isMiscompiled()):
            (gDim, lDim) = self.updateDimensions(newGlobalDim, newLocalDim)

            if gDim == newGlobalDim and lDim == newLocalDim:
                return None
            else:
                newGlobalDim = gDim
                newLocalDim = lDim

            self.rewriteDimensions(newGlobalDim, newLocalDim)

        return (newGlobalDim, newLocalDim)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('No file specified!')
        sys.exit(1)

    kernelFile = sys.argv[1]

    testPlatform = os.environ.get('CREDUCE_TEST_PLATFORM')
    if not testPlatform:
        print('CREDUCE_TEST_PLATFORM not defined!')
        sys.exit(1)

    testDevice = os.environ.get('CREDUCE_TEST_DEVICE')
    if not testDevice:
        print('CREDUCE_TEST_DEVICE not defined!')
        sys.exit(1)

    clLauncher = os.environ.get('CREDUCE_TEST_CLLAUNCHER', os.path.abspath('./cl_launcher'))
    if not which(clLauncher):
        clLauncher = os.path.basename(clLauncher)

        if not which(clLauncher):
            print('CREDUCE_TEST_CLLAUNCHER not defined and cl_launcher not found!')
            sys.exit(1)

    clang = os.environ.get('CREDUCE_TEST_CLANG', os.path.abspath('./clang'))
    if not which(clang):
        clang = os.path.basename(clang)

        if not which(clang):
            print('CREDUCE_TEST_CLANG not defined and clang not found!')
            sys.exit(1)

    libclcIncludePath = os.environ.get('CREDUCE_LIBCLC_INCLUDE_PATH')

    if sys.platform == 'win32':
        openCLEnv = openCLTest.WinOpenCLEnv(clLauncher, clang, libclcIncludePath, 0, 0)
    else:
        openCLEnv = openCLTest.UnixOpenCLEnv(clLauncher, clang, libclcIncludePath)

    kernelTest = openCLTest.InterestingnessTest(openCLEnv, kernelFile, testPlatform, testDevice)
    dimReducer = DimensionReducer(kernelFile, kernelTest)
    result = dimReducer.reduce()

    if not result:
        print("File cannot be miscompiled!")
        sys.exit(1)
    else:
        print('Reduced dimensions to %s' % str(result))
