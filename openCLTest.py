#!/usr/bin/env python3

import sys, os, re, subprocess, signal, argparse

def which(cmd):
    if sys.platform == 'win32' and '.' not in cmd:
        cmd += '.exe'

    if os.path.isfile(cmd) and os.access(cmd, os.F_OK | os.X_OK):
        return cmd

    for path in os.environ["PATH"].split(os.pathsep):
        compoundPath = os.path.join(path, cmd)

        if os.path.isfile(compoundPath) and os.access(compoundPath, os.F_OK | os.X_OK):
            return compoundPath

    return None

class InterestingnessTest:
    availableTests = ['miscompilation', 'crash-unoptimised', 'error-vector', 'statically-valid', 'valid', 'csa-invalid', 'oclgrind-miscompilation', 'oclgrind-optimised', 'oclgrind-uninitialized', 'wrong-code']

    def __init__(self, test, openCLEnv, kernelName, testPlatform, testDevice, outputFile = None, progressFile = None):
        self.test = test
        self.openCLEnv = openCLEnv
        self.kernelName = kernelName
        self.testPlatform = testPlatform
        self.testDevice = testDevice
        self.outputFile = outputFile
        self.progressFile = progressFile

        with open(kernelName, 'r') as f:
            self.kernelContent = f.read()

    def logProgress(self, msg):
        if self.progressFile:
            print(msg, file = self.progressFile)

    def logOutput(self, output):
        if self.outputFile:
            print(output, file=self.outputFile)

    def getWorkItemCount(self):
        m = re.match('//.* -g ([0-9]+),([0-9]+),([0-9]+) -l ([0-9]+),([0-9]+),([0-9]+)', self.kernelContent)

        if m == None:
            return None

        return int(m.group(1)) * int(m.group(2)) * int(m.group(3))

    def isValidResultAccess(self):
        return not re.search('result\s*\[', self.kernelContent) or re.search('result\s*\[\s*get_linear_global_id\s*\(\s*\)\s*\]', self.kernelContent)

    def isValidClang(self):
        clangInvocation = self.openCLEnv.runClangCL([self.kernelName], 300)

        if clangInvocation is not None and clangInvocation[1] == 0:
            self.logOutput(clangInvocation[0])

            if ('warning: empty struct is a GNU extension' not in clangInvocation[0] and
                'warning: use of GNU empty initializer extension' not in clangInvocation[0] and
                'warning: incompatible pointer to integer conversion' not in clangInvocation[0] and
                'warning: incompatible integer to pointer conversion' not in clangInvocation[0] and
                'warning: incompatible pointer types initializing' not in clangInvocation[0] and
                'warning: comparison between pointer and integer' not in clangInvocation[0] and
                'warning: ordered comparison between pointer and integer' not in clangInvocation[0] and
                'warning: ordered comparison between pointer and zero' not in clangInvocation[0] and
                'is uninitialized when used within its own initialization [-Wuninitialized]' not in clangInvocation[0] and
                'is uninitialized when used here [-Wuninitialized]' not in clangInvocation[0] and
                'may be uninitialized when used here [-Wconditional-uninitialized]' not in clangInvocation[0] and
                'warning: use of GNU ?: conditional expression extension, omitting middle operand' not in clangInvocation[0] and
                'warning: control may reach end of non-void function [-Wreturn-type]' not in clangInvocation[0] and
                'warning: control reaches end of non-void function [-Wreturn-type]' not in clangInvocation[0] and
                'warning: zero size arrays are an extension [-Wzero-length-array]' not in clangInvocation[0] and
                'excess elements in ' not in clangInvocation[0] and
                'warning: address of stack memory associated with local variable' not in clangInvocation[0] and
                'warning: type specifier missing' not in clangInvocation[0] and
                "warning: expected ';' at end of declaration list" not in clangInvocation[0] and
                ' declaration specifier [-Wduplicate-decl-specifier]' not in clangInvocation[0]):
                return True

        return False

    def isValidClangAnalyzer(self):
        return True
        clangAnalyzerInvocation = self.openCLEnv.runClangStaticAnalyzer([self.kernelName], 300)

        if clangAnalyzerInvocation is not None and clangAnalyzerInvocation[1] == 0:
            self.logOutput(clangAnalyzerInvocation[0])

            if ('warning: Assigned value is garbage or undefined' not in clangAnalyzerInvocation[0] and
                'warning: Undefined or garbage value returned to caller' not in clangAnalyzerInvocation[0] and
                'is a garbage value' not in clangAnalyzerInvocation[0] and
                'warning: Dereference of null pointer' not in clangAnalyzerInvocation[0] and
                'warning: Array subscript is undefined' not in clangAnalyzerInvocation[0] and
                'results in a dereference of a null pointer' not in clangAnalyzerInvocation[0]):
                return True

        return False

    def isValidCLLauncherKernel(self):
        # Make sure comment with dimensions is preserved
        self.logProgress('Dimension')
        m = re.match('//.* -g [0-9]+,[0-9]+,[0-9]+ -l [0-9]+,[0-9]+,[0-9]+', self.kernelContent)

        if m == None:
            return False

        #grep -E '// Seed: [0-9]+' ${KERNEL} > /dev/null 2>&1 &&\

        # Access to result only with get_linear_global_id()
        self.logProgress('Result')
        if not self.isValidResultAccess():
            return False

        # Must not change get_linear_global_id
        # TODO: Improve
        # TODO: Do I need this or will Oclgrind check it too
        self.logProgress('Id')
        if not re.search('return\s*\(\s*get_global_id\s*\(\s*2\s*\)\s*\*\s*get_global_size\s*\(\s*1\s*\)\s*\+\s*get_global_id\s*\(\s*1\s*\)\s*\)\s*\*\s*get_global_size\s*\(\s*0\s*\)\s*\+\s*get_global_id\s*\(\s*0\s*\)\s*;', self.kernelContent):
            return False

        return True

    def isStaticallyValid(self):
        # Run static analysis of the program
        # Better support for uninitialised values
        self.logProgress('Clang CL')
        if not self.isValidClang():
            return False

        self.logProgress('Clang Static Analyzer')
        if not self.isValidClangAnalyzer():
            return False

        return True

    def isValidOclgrind(self):
        oclgrindInvocationOpt = self.openCLEnv.runOclgrindClLauncher(self.kernelName, 300, optimised = True)
        oclgrindInvocationUnopt = self.openCLEnv.runOclgrindClLauncher(self.kernelName, 300, optimised = False)

        if (oclgrindInvocationOpt is not None and
                oclgrindInvocationUnopt is not None and
                oclgrindInvocationOpt[1] == 0 and
                oclgrindInvocationUnopt[1] == 0):
            return True

        return False

    def isMiscompiled(self):
        self.logProgress('Run optimised')
        optimisedInvocation = self.openCLEnv.runKernel(self.testPlatform, self.testDevice, self.kernelName, 300)
        if optimisedInvocation:
            self.logProgress('Optimised result: ' + optimisedInvocation[0]);
        if optimisedInvocation is None or optimisedInvocation[1] != 0:
            return False

        self.logProgress('Run unoptimised')
        unoptimisedInvocation = self.openCLEnv.runKernel(self.testPlatform, self.testDevice, self.kernelName, 300, optimised = False)
        if unoptimisedInvocation:
            self.logProgress('Unoptimised result: ' + unoptimisedInvocation[0]);
        if unoptimisedInvocation is None or unoptimisedInvocation[1] != 0:
            return False

        self.logProgress('Diff')
        if optimisedInvocation[0] == unoptimisedInvocation[0]:
            return False

        return True

    def isMiscompiledOclgrind(self):
        self.logProgress('Run optimised')
        optimisedInvocation = self.openCLEnv.runOclgrindClLauncher(self.kernelName, 300)
        if optimisedInvocation is None or optimisedInvocation[1] != 0:
            return False

        self.logProgress('Run unoptimised')
        unoptimisedInvocation = self.openCLEnv.runOclgrindClLauncher(self.kernelName, 300, optimised = False)
        if unoptimisedInvocation is None or unoptimisedInvocation[1] != 0:
            return False

        self.logProgress('Diff')
        if optimisedInvocation[0] == unoptimisedInvocation[0]:
            return False

        return True

    #def isFalsePositiveUninitializedOclgrind(self):
    #    oclgrindArgsNew = ['-Wall', '--memcheck-uninitialized', '--data-races', '--uniform-writes']
    #    oclgrindArgsOld = ['-Wall', '--uninitialized', '--data-races', '--uniform-writes']
    #    args = ['-p', '0', '-d', '0', '-f', self.kernelName]

    #    oclgrindNewInvocation = self.openCLEnv.check_output(['oclgrind'] + oclgrindArgsNew + [self.openCLEnv.clLauncher] + args, 300)
    #    oclgrindOldInvocation = self.openCLEnv.check_output(['oclgrind'] + oclgrindArgsOld + [self.openCLEnv.clLauncher] + args, 300)

    #    if oclgrindNewInvocation is None or oclgrindNewInvocation[1] != 0 or oclgrindOldInvocation is None or oclgrindOldInvocation[1] != 0:
    #        return False

    #    if 'Controlflow depends on uninitialized value' not in oclgrindNewInvocation[0] or 'call spir_func <2 x i32> @_Z7sub_satDv2_iS_' not in oclgrindNewInvocation[0]:
    #        return False

    #    if 'call spir_func <2 x i32> @_Z7sub_satDv2_iS_' in oclgrindOldInvocation[0]:
    #        return False

    #    self.logProgress('Oclgrind false positive')

    #    return True

    def isValid(self):
        if not self.isValidCLLauncherKernel():
            return False

        if not self.isStaticallyValid():
            return False

        self.logProgress('Run Oclgrind')
        if not self.isValidOclgrind():
            return False

        return True

    def isValidMiscompilation(self):
        if not self.isValid():
            return False

        if not self.isMiscompiled():
            return False

        self.logProgress('Different')

        return True

    def isValidMiscompilationOclgrind(self):
        if not self.isValid():
            return False

        if not self.isMiscompiledOclgrind():
            return False

        self.logProgress('Different')

        return True

    def isCompilerCrashUnoptimised(self):
        if not self.isValidCLLauncherKernel():
            return False

        if not self.isStaticallyValid():
            return False

        self.logProgress('Run Oclgrind')
        if not self.isValidOclgrind():
            return False

        self.logProgress('Run optimised')
        optimisedInvocation = self.openCLEnv.runKernel(self.testPlatform, self.testDevice, self.kernelName, 300)
        if optimisedInvocation is None or optimisedInvocation[1] != 0:
            return False

        self.logProgress('Run unoptimised')
        unoptimisedInvocation = self.openCLEnv.runKernel(self.testPlatform, self.testDevice, self.kernelName, 300, optimised = False)
        if unoptimisedInvocation is not None and unoptimisedInvocation[1] == 0:
            return False

        self.logProgress('Crash unoptimised')

        return True

    def hasClangError(self, err):
        clangInvocation = self.openCLEnv.runClangCL([self.kernelName], 300)

        if clangInvocation is None or clangInvocation[1] == 0:
            return False

        if err not in clangInvocation[0]:
            return False

        self.logProgress('Vector crash')

        return True

    def runTest(self):
        if self.test == 'crash-unoptimised':
            return self.isCompilerCrashUnoptimised()
        elif self.test == 'wrong-code':
            return self.isMiscompiled()
        elif self.test == 'miscompilation':
            return self.isValidMiscompilation()
        elif self.test == 'oclgrind-miscompilation':
            return self.isValidMiscompilationOclgrind()
        elif self.test == 'oclgrind-optimised':
            return self.openCLEnv.runOclgrindClLauncher(self.kernelName, 300) is not None
        elif self.test == 'oclgrind-uninitialized':
            print('Deprecated!', file=sys.stderr)
            return False
        #    return self.isFalsePositiveUninitializedOclgrind()
        elif self.test == 'statically-valid':
            return self.isStaticallyValid()
        elif self.test == 'csa-invalid':
            if not self.isValidClang():
                return False

            if self.isValidClangAnalyzer():
                return False

            return self.openCLEnv.runOclgrindClLauncher(self.kernelName, 300, False) is not None
        elif self.test == 'error-vector':
            if not self.isValidCLLauncherKernel():
                return False

            if not self.hasClangError("error: can't convert between vector values of different size"):
                return False

            optimisedInvocation = self.openCLEnv.runKernel(self.testPlatform, self.testDevice, self.kernelName, 300)
            if optimisedInvocation is None or optimisedInvocation[1] != 0:
                return False

            return True
        elif self.test == 'valid':
            return self.isValid()

        return False

class OpenCLEnv:
    def __init__(self, clLauncher, clang, libclcIncludePath):
        self.clLauncher = clLauncher
        self.clang = clang
        self.libclcIncludePath = libclcIncludePath

        self.oclgrindPlatform = 0
        self.oclgrindDevice = 0

    def check_output(self, args, timeLimit):
        try:
            output = subprocess.check_output(args, universal_newlines=True, stderr=subprocess.STDOUT, timeout=timeLimit)
            return (output, 0)
        except subprocess.CalledProcessError as err:
            return (err.output, err.returncode)
        except subprocess.SubprocessError:
            return None

    def runClangCL(self, args, timeLimit):
        oclArgs = ['-x', 'cl', '-fno-builtin', '-include', 'clc/clc.h', '-Dcl_clang_storage_class_specifiers']

        if self.libclcIncludePath:
            oclArgs.extend(['-I', self.libclcIncludePath])

        diagArgs = ['-g', '-c', '-Wall', '-Wextra', '-pedantic', '-Wconditional-uninitialized', '-Weverything', '-Wno-reserved-id-macro', '-fno-caret-diagnostics', '-fno-diagnostics-fixit-info', '-O1']
        print(" ".join([self.clang] + oclArgs + diagArgs + args))
        return self.check_output([self.clang] + oclArgs + diagArgs + args, timeLimit)

    def runClangStaticAnalyzer(self, args, timeLimit):
        #TODO: Maybe use scan-build?!
        #analysisArgs = ['-Xclang', '-analyze', '-Xclang', '-analyzer-checker', '-Xclang', 'alpha,core,security,unix']
        analysisArgs = ['--analyze', '-Xclang', '-analyzer-checker', '-Xclang', 'alpha,core,security,unix']
        return self.runClangCL(analysisArgs + args, timeLimit)

    def runOclgrindClLauncher(self, kernel, timeLimit, optimised = True):
        return None

    def runKernel(self, platform, device, kernel, timeLimit, optimised = True):
        args = [self.clLauncher, '-p', str(platform), '-d', str(device), '-f', kernel]

        if not optimised:
            args.append('---disable_opts')

        return self.check_output(args, timeLimit)

class UnixOpenCLEnv(OpenCLEnv):
    def check_output(self, args, timeLimit):
        try:
            proc = subprocess.Popen(args, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            output, _ = proc.communicate(timeout=timeLimit)
            return (output, proc.returncode)
        except subprocess.SubprocessError:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.communicate()

        return None

    def runOclgrindClLauncher(self, kernel, timeLimit, optimised = True):
        oclgrindArgs = ['-Wall', '--uninitialized', '--data-races', '--uniform-writes', '--stop-errors', '1']
        args = ['-p', str(self.oclgrindPlatform), '-d', str(self.oclgrindDevice), '-f', kernel]

        if not optimised:
            args.append('---disable_opts')

        print(" ".join(['oclgrind'] + oclgrindArgs + [self.clLauncher] + args))
        return self.check_output(['oclgrind'] + oclgrindArgs + [self.clLauncher] + args, timeLimit)

class WinOpenCLEnv(OpenCLEnv):
    def __init__(self, clLauncher, clang, libclcIncludePath, oclgrindPlatform, oclgrindDevice):
        super().__init__(clLauncher, clang, libclcIncludePath)

        self.oclgrindPlatform = oclgrindPlatform
        self.oclgrindDevice = oclgrindDevice

    def check_output(self, args, timeLimit, env=os.environ):
        try:
            proc = subprocess.Popen(args, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP, env=env)
            output, _ = proc.communicate(timeout=timeLimit)
            return (output, proc.returncode)
        except subprocess.SubprocessError:
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            proc.communicate()

        return None

    def runOclgrindClLauncher(self, kernel, timeLimit, optimised = True):
        oclgrindEnv = os.environ
        oclgrindEnv['OCLGRIND_DIAGNOSTIC_OPTIONS'] = '-Wall'
        oclgrindEnv['OCLGRIND_MEMCHECK_UNINITIALIZED'] = '1'
        oclgrindEnv['OCLGRIND_DATA_RACES'] = '1'
        oclgrindEnv['OCLGRIND_STOP_ERRORS'] = '1'
        args = ['-p', str(self.oclgrindPlatform), '-d', str(self.oclgrindDevice), '-f', kernel]

        if not optimised:
            args.append('---disable_opts')

        return self.check_output([self.clLauncher] + args, timeLimit, env=oclgrindEnv)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Interestingness tests for OpenCL kernels.')
    parser.add_argument('--test', choices=InterestingnessTest.availableTests, default=InterestingnessTest.availableTests[0], help='Interestingness test')
    parser.add_argument('kernel', nargs='?', help='Filename of the OpenCL kernel')

    args = parser.parse_args()

    kernelName = os.environ.get('CREDUCE_TEST_KERNEL', 'CLProg.cl')

    if args.kernel:
        kernelName = args.kernel

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
            print('cl_launcher not found and CREDUCE_TEST_CLLAUNCHER not defined!')
            sys.exit(1)

    clang = os.environ.get('CREDUCE_TEST_CLANG', os.path.abspath('./clang'))
    if not which(clang):
        clang = os.path.basename(clang)

        if not which(clang):
            print('CREDUCE_TEST_CLANG not defined and clang not found!')
            sys.exit(1)

    libclcIncludePath = os.environ.get('CREDUCE_LIBCLC_INCLUDE_PATH')

    outputFile = None
    if os.environ.get('CREDUCE_TEST_LOG'):
        outputFile = open('output.log', 'a');

    progressFile = None
    if os.environ.get('CREDUCE_TEST_DEBUG'):
        progressFile = sys.stdout

    if sys.platform == 'win32':
        oclgrindPlatform = os.environ.get('CREDUCE_TEST_OCLGRIND_PLATFORM')
        if not oclgrindPlatform:
            print('CREDUCE_TEST_OCLGRIND_PLATFORM not defined!')
            sys.exit(1)

        oclgrindDevice = os.environ.get('CREDUCE_TEST_OCLGRIND_DEVICE')
        if not oclgrindDevice:
            print('CREDUCE_TEST_OCLGRIND_DEVICE not defined!')
            sys.exit(1)

        openCLEnv = WinOpenCLEnv(clLauncher, clang, libclcIncludePath, oclgrindPlatform, oclgrindDevice)
    else:
        openCLEnv = UnixOpenCLEnv(clLauncher, clang, libclcIncludePath)

    kernelTest = InterestingnessTest(args.test, openCLEnv, kernelName, testPlatform, testDevice, outputFile=outputFile, progressFile=progressFile)
    isSuccessfulTest = kernelTest.runTest()

    if outputFile:
        outputFile.close()

    if not isSuccessfulTest:
        sys.exit(1)
    else:
        sys.exit(0)
