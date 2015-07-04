#!/usr/bin/env python3

import sys, os, re, openCLTest

class DimensionReducer:
    def __init__(self, kernelFile):
        self.kernelFile = open(kernelFile, 'r+')
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

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('No file specified!')
        sys.exit(1)

    kernelFile = sys.argv[1]
    dimReducer = DimensionReducer(kernelFile)

    testPlatform = os.environ.get('CREDUCE_TEST_PLATFORM')
    if not testPlatform:
        print('CREDUCE_TEST_PLATFORM not defined!')
        sys.exit(1)

    testDevice = os.environ.get('CREDUCE_TEST_DEVICE')
    if not testDevice:
        print('CREDUCE_TEST_DEVICE not defined!')
        sys.exit(1)

    clLauncher = os.environ.get('CREDUCE_TEST_CLLAUNCHER')
    if not clLauncher:
        print('CREDUCE_TEST_CLLAUNCHER not defined!')
        sys.exit(1)

    clang = os.environ.get('CREDUCE_TEST_CLANG')
    if not clang:
        print('CREDUCE_TEST_CLANG not defined!')
        sys.exit(1)

    libclcIncludePath = os.environ.get('CREDUCE_TEST_LIBCLC_INCLUDE_PATH')
    if not libclcIncludePath:
        print('CREDUCE_TEST_LIBCLC_INCLUDE_PATH not defined!')
        sys.exit(1)

    if sys.platform == 'win32':
        openCLEnv = openCLTest.WinOpenCLEnv(clLauncher, clang, libclcIncludePath, 0, 0)
    else:
        openCLEnv = openCLTest.UnixOpenCLEnv(clLauncher, clang, libclcIncludePath)

    kernelTest = openCLTest.InterestingnessTest(openCLEnv, kernelFile, testPlatform, testDevice)

    newGlobalDim = (1,1,1)
    newLocalDim = (1,1,1)

    dimReducer.rewriteDimensions(newGlobalDim, newLocalDim)

    while(not kernelTest.isMiscompiled()):
        (gDim, lDim) = dimReducer.updateDimensions(newGlobalDim, newLocalDim)

        if gDim == newGlobalDim and lDim == newLocalDim:
            print("File cannot be miscompiled!")
            sys.exit(1)
        else:
            newGlobalDim = gDim
            newLocalDim = lDim

        dimReducer.rewriteDimensions(newGlobalDim, newLocalDim)

    print('Reduced dimensions to %s, %s' % (newGlobalDim, newLocalDim))
