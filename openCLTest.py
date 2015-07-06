#!/usr/bin/env python3

import sys, os, re, subprocess, signal

class InterestingnessTest:
    def __init__(self, openCLEnv, kernelName, testPlatform, testDevice, outputFile = None, progressFile = None):
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

    def isValidStruct(self):
        # Get name of struct that gets assigned
        # It is always the first struct in the entry kernel
        m = re.search('struct\s+S\d+\s+c_(\d+)\s*;', self.kernelContent)

        if m == None:
            self.logProgress('   -> No struct')
            return True

        structNumber = m.group(1)

        # Check if the pointer to the struct is initialised
        m = re.search('struct\s+S\d+(:?\s*\*\s+|\s+\*\s*)p_\d+\s*=\s*&\s*c_' + structNumber + '\s*;', self.kernelContent)

        if m == None:
            self.logProgress('   -> Uninitialised pointer')
            return False

        # Check if there is an assigment for that struct
        m = re.search('c_' + structNumber + '\s*=\s*c_(\d+)\s*;', self.kernelContent)

        if m == None:
            self.logProgress('   -> No assignment')
            return False

        structNumber = m.group(1)

        # Check if assigned value has been initialised
        m = re.search('struct\s+S\d+\s+c_' + structNumber + '\s*=\s*{', self.kernelContent)

        if m == None:
            self.logProgress('   -> Uninitialised value')
            return False

        return True

    def isValidResultAccess(self):
        return not re.search('result\s*\[', self.kernelContent) or re.search('result\s*\[\s*get_linear_global_id\s*\(\s*\)\s*\]', self.kernelContent)

    def checkClang(self):
        outputClang = self.openCLEnv.runClangCL([self.kernelName], 300)

        if outputClang:
            self.logOutput(outputClang)

            if ('warning: empty struct is a GNU extension' not in outputClang and
                'warning: use of GNU empty initializer extension' not in outputClang and
                'warning: incompatible pointer to integer conversion' not in outputClang and
                'warning: incompatible integer to pointer conversion' not in outputClang and
                'warning: incompatible pointer types initializing' not in outputClang and
                'may be uninitialized when used here [-Wconditional-uninitialized]' not in outputClang and
                'warning: use of GNU ?: conditional expression extension, omitting middle operand' not in outputClang and
                'warning: control may reach end of non-void function [-Wreturn-type]' not in outputClang and
                'warning: control reaches end of non-void function [-Wreturn-type]' not in outputClang and
                'warning: zero size arrays are an extension [-Wzero-length-array]' not in outputClang and
                'excess elements in ' not in outputClang and
                'warning: address of stack memory associated with local variable' not in outputClang and
                ' declaration specifier [-Wduplicate-decl-specifier]' not in outputClang):
                return True

        return False

    def checkClangAnalyzer(self):
        outputClangAnalyzer = self.openCLEnv.runClangStaticAnalyzer([self.kernelName], 300)

        if outputClangAnalyzer:
            self.logOutput(outputClangAnalyzer)

            if ('warning: Assigned value is garbage or undefined' not in outputClangAnalyzer and
                'is a garbage value' not in outputClangAnalyzer and
                'warning: Dereference of null pointer' not in outputClangAnalyzer and
                'results in a dereference of a null pointer' not in outputClangAnalyzer):
                return True

        return False

    def checkOclgrind(self):
        outputOclgrind = self.openCLEnv.runOclgrindClLauncher(self.kernelName, 300, optimised = False)

        if outputOclgrind:
            self.logOutput(outputOclgrind)

            if ('Work-group divergence detected' not in outputOclgrind and
                'Invalid memory load' not in outputOclgrind and
                'Invalid memory store' not in outputOclgrind and
                'Unaligned address on ' not in outputOclgrind and
                'exceeds static array size' not in outputOclgrind and
                'Invalid read from write-only buffer' not in outputOclgrind and
                'Invalid write to read-only buffer' not in outputOclgrind and
                'Invalid read of size' not in outputOclgrind and
                'Invalid write of size' not in outputOclgrind and
                ' data race at ' not in outputOclgrind and
                #'Uninitialized value read from ' not in outputOclgrind and
                'OCLGRIND FATAL ERROR ' not in outputOclgrind and
                self.checkOclgrindUninitialised(outputOclgrind)):
                return True

        return False

    def checkOclgrindUninitialised(self, outputOclgrind):
        countUninitialisedWarnings = outputOclgrind.count('Uninitialized value read from private memory address')
        return countUninitialisedWarnings == 0 or countUninitialisedWarnings == self.getWorkItemCount()

    def isMiscompiled(self):
        self.logProgress('Run optimised')
        outputOptimised = self.openCLEnv.runKernel(self.testPlatform, self.testDevice, self.kernelName, 300)
        if not outputOptimised:
            return False

        self.logProgress('Run unoptimised')
        outputUnoptimised = self.openCLEnv.runKernel(self.testPlatform, self.testDevice, self.kernelName, 300, optimised = False)
        if not outputUnoptimised:
            return False

        self.logProgress('Diff')
        if outputOptimised == outputUnoptimised:
            return False

        return True

    def isValidMiscompilation(self):
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
        self.logProgress('Id')
        if not re.search('return\s*\(\s*get_global_id\s*\(\s*2\s*\)\s*\*\s*get_global_size\s*\(\s*1\s*\)\s*\+\s*get_global_id\s*\(\s*1\s*\)\s*\)\s*\*\s*get_global_size\s*\(\s*0\s*\)\s*\+\s*get_global_id\s*\(\s*0\s*\)\s*;', self.kernelContent):
            return False

        # Prevent uninitialised structs
        self.logProgress('Struct')
        if not self.isValidStruct():
            return False

        # Run static analysis of the program
        # Better support for uninitialised values
        self.logProgress('Clang CL')
        if not self.checkClang():
            return False

        self.logProgress('Clang Static Analyzer')
        if not self.checkClangAnalyzer():
            return False

#logProgress "Verify" && ${CREDUCE_TEST_TIMEOUT_TOOL} 60 ${GPUVERIFY_LAUNCHER} --local_size=1 --global_size=1 --stop-at-opt ${KERNEL} > out_verifier.txt 2>&1 && logOutput out_verifier.txt &&\
#! grep 'warning: control reaches end of non-void function \[-Wreturn-type\]' out_verifier.txt > /dev/null 2>&1 &&\
#! grep "warning: expected ';' at end of declaration list" out_verifier.txt > /dev/null 2>&1 &&\
#! grep "uninitialized" out_verifier.txt > /dev/null 2>&1 &&\
#! grep "type specifier missing" out_verifier.txt > /dev/null 2>&1 &&\

        self.logProgress('Run Oclgrind')
        if not self.checkOclgrind():
            return False

        if not self.isMiscompiled():
            return False

        self.logProgress('Different')

        return True

class OpenCLEnv:
    def __init__(self, clLauncher, clang, libclcIncludePath):
        self.clLauncher = clLauncher
        self.clang = clang
        self.libclcIncludePath = libclcIncludePath

        self.oclgrindPlatform = 0
        self.oclgrindDevice = 0

    def check_output(self, args, timeLimit):
        try:
            return subprocess.check_output(args, universal_newlines=True, stderr=subprocess.STDOUT, timeout=timeLimit)
        except sunprocess.SubprocessError:
            return None

    def runClangCL(self, args, timeLimit):
        oclArgs = ['-x', 'cl', '-fno-builtin', '-I', self.libclcIncludePath, '-include', 'clc/clc.h', '-Dcl_clang_storage_class_specifiers']
        diagArgs = ['-g', '-c', '-Wall', '-Wextra', '-pedantic', '-Wconditional-uninitialized', '-Weverything', '-Wno-reserved-id-macro', '-fno-caret-diagnostics', '-fno-diagnostics-fixit-info', '-O1']
        return self.check_output([self.clang] + oclArgs + diagArgs + args, timeLimit)

    def runClangStaticAnalyzer(self, args, timeLimit):
        analysisArgs = ['-Xclang', '-analyze', '-Xclang', '-analyzer-checker', '-Xclang', 'alpha,core,security,unix']
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
            if proc.returncode == 0:
                return output
        except subprocess.SubprocessError:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.communicate()

        return None

    def runOclgrindClLauncher(self, kernel, timeLimit, optimised = True):
        oclgrindArgs = ['-Wall', '--uninitialized', '--data-races']
        args = ['-p', str(self.oclgrindPlatform), '-d', str(self.oclgrindDevice), '-f', kernel]

        if not optimised:
            args.append('---disable_opts')

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
            if proc.returncode == 0:
                return output
        except subprocess.SubprocessError:
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            proc.communicate()

        return None

    def runOclgrindClLauncher(self, kernel, timeLimit, optimised = True):
        oclgrindEnv = os.environ
        oclgrindEnv['OCLGRIND_DIAGNOSTIC_OPTIONS'] = '-Wall'
        oclgrindEnv['OCLGRIND_UNINITIALIZED'] = '1'
        oclgrindEnv['OCLGRIND_DATA_RACES'] = '1'
        args = ['-p', str(self.oclgrindPlatform), '-d', str(self.oclgrindDevice), '-f', kernel]

        if not optimised:
            args.append('---disable_opts')

        return self.check_output([self.clLauncher] + args, timeLimit, env=oclgrindEnv)

if __name__ == "__main__":
    kernelName = os.environ.get('CREDUCE_TEST_KERNEL', 'CLProg.cl')

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

    clang = os.environ.get('CREDUCE_TEST_CLANG', 'clang')

    libclcIncludePath = os.environ.get('CREDUCE_TEST_LIBCLC_INCLUDE_PATH')
    if not libclcIncludePath:
        print('CREDUCE_TEST_LIBCLC_INCLUDE_PATH not defined!')
        sys.exit(1)

    if len(sys.argv) > 1:
        kernelName = sys.argv[1]

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

    kernelTest = InterestingnessTest(openCLEnv, kernelName, testPlatform, testDevice, outputFile=outputFile, progressFile=progressFile)

    isMiscompilation = kernelTest.isValidMiscompilation()

    if outputFile:
        outputFile.close()

    if not isMiscompilation:
        sys.exit(1)
    else:
        sys.exit(0)
